import re
from typing import Optional, List, Dict, Any
from core.state import AgentState, TravelSlots, Slot, SlotStatus, StepStatus
from core.tools_interface import TravelTools, Bundle
from core.mock_tools import MockTravelTools
from core.llm_client import LLMClient


class AgentWorkflow:
    """
    Главный оркестратор (State Machine) AI-агента.
    Управляет переходами: Блокеры -> Эвристики -> Поиск / Конфликты -> Точечная пересборка -> Post-booking.
    """

    def __init__(
        self,
        tools: Optional[TravelTools] = None,
        llm_client: Optional[LLMClient] = None
    ):
        # Автономные инструменты (моки или реальная БД)
        self.tools: TravelTools = tools or MockTravelTools()
        # NLU-клиент для Qwen
        self.llm: LLMClient = llm_client or LLMClient()
        # Кэш направлений для этапа вдохновения
        self.last_destination_suggestions: List[Dict[str, Any]] = []
        # Хранилище ответа консьержа пост-букинга
        self.last_post_booking_result: Optional[Dict[str, Any]] = None

    # =========================================================================
    # 1. BLOCKER ALGORITHM (Охранный узел)
    # =========================================================================
    def check_blockers_node(self, state: AgentState) -> AgentState:
        """
        Проверяет обязательное трио параметров:
        1. origin (откуда)
        2. dates (когда)
        3. destination ИЛИ vibe (куда / зачем)
        Если чего-то нет — прерывает пайплайн и формирует ровно 1 вопрос.
        """
        slots = state.slots

        # 1. Проверяем город отправления
        if slots.origin.status == SlotStatus.NO or not slots.origin.value:
            state.clarification_question = "Подскажите, из какого города вы планируете вылет или выезд?"
            state.current_step = StepStatus.WAIT_USER_INPUT
            state.clarification_count += 1
            return state

        # 2. Проверяем даты или сезон
        if slots.dates.status == SlotStatus.NO or not slots.dates.value:
            state.clarification_question = "На какие даты или в каком месяце планируется поездка?"
            state.current_step = StepStatus.WAIT_USER_INPUT
            state.clarification_count += 1
            return state

        # 3. Проверяем цель поездки (взаимозаменяемые destination OR vibe)
        has_destination = slots.destination.status != SlotStatus.NO and bool(slots.destination.value)
        has_vibe = slots.vibe.status != SlotStatus.NO and bool(slots.vibe.value)

        if not (has_destination or has_vibe):
            state.clarification_question = (
                "Куда бы вы хотели отправиться или какой формат отдыха вам ближе "
                "(например, тёплое море, горы, экскурсии)?"
            )
            state.current_step = StepStatus.WAIT_USER_INPUT
            state.clarification_count += 1
            return state

        # Все блокеры пройдены
        state.clarification_question = None
        state.current_step = StepStatus.BLOCKERS_PASSED
        return state

    # =========================================================================
    # 2. VAGUE SLOTS RESOLUTION (Эвристики для размытых параметров)
    # =========================================================================
    def resolve_vague_slots_node(self, state: AgentState) -> AgentState:
        """
        Заменяет размытые слоты (VAGUE) конкретными параметрами перед походом в БД:
        - Подбирает направления по вайбу и сезону (с визой и без визы).
        - Оцифровывает размытый бюджет ('недорого', 'средний').
        - Нормализует звёздность отеля.
        """
        slots = state.slots

        # Эвристика 1: Нет конкретного направления, но есть вайб (Этап «Вдохновение»)
        if (slots.destination.status == SlotStatus.NO or not slots.destination.value) and slots.vibe.value:
            vibe_str = str(slots.vibe.value)
            month_str = str(slots.dates.value)
            visa_pref = str(slots.visa.value) if slots.visa.value else None

            suggestions = self.tools.search_destinations(
                vibe=vibe_str,
                month=month_str,
                visa_preference=visa_pref
            )
            self.last_destination_suggestions = [s.model_dump() for s in suggestions]

            if suggestions:
                chosen = suggestions[0]
                slots.destination.value = chosen.destination
                slots.destination.status = SlotStatus.VAGUE
                state.applied_heuristics.append(
                    f"Подобрано направление '{chosen.destination}' под вайб '{vibe_str}' "
                    f"({chosen.weather_summary}, мин. бюджет ~{chosen.estimated_min_budget} ₽)"
                )

        # Эвристика 2: Размытый бюджет ("недорого", "бюджетно", "люкс") или строка с числом
        if slots.budget.value is not None:
            raw_budget = str(slots.budget.value).lower()
            if isinstance(slots.budget.value, str):
                digits = re.findall(r"\d+", raw_budget)
                if digits:
                    num = int(digits[0])
                    if num < 1000 and ("тыс" in raw_budget or "к" in raw_budget or "k" in raw_budget):
                        num *= 1000
                    slots.budget.value = num
                    slots.budget.status = SlotStatus.YES
                elif any(w in raw_budget for w in ["недорог", "дешев", "эконом", "бюджет"]):
                    slots.budget.value = 95000
                    slots.budget.status = SlotStatus.VAGUE
                    state.applied_heuristics.append("Размытый бюджет 'недорого' переведён в лимит до 95 000 ₽")
                elif any(w in raw_budget for w in ["люкс", "премиум", "дорог", "шикарн"]):
                    slots.budget.value = 250000
                    slots.budget.status = SlotStatus.VAGUE
                    state.applied_heuristics.append("Размытый бюджет 'премиум' переведён в лимит до 250 000 ₽")

        # Эвристика 3: Нормализация звёздности отеля (например, "4*" -> 4)
        if slots.stars.value is not None and not isinstance(slots.stars.value, int):
            digits = re.findall(r"[345]", str(slots.stars.value))
            if digits:
                slots.stars.value = int(digits[0])

        state.current_step = StepStatus.VAGUE_RESOLVED
        return state

    # =========================================================================
    # 3. SURGICAL INVALIDATION (Точечная пересборка без сброса контекста)
    # =========================================================================
    def can_do_surgical_hotel_rebuild(self, state: AgentState) -> bool:
        """
        Проверяет, можно ли пересобрать ТОЛЬКО отель, не трогая авиабилеты:
        - Уже есть рекомендации или собранная корзина;
        - Транспорт всё ещё валиден (is_transport_valid == True);
        - Отель помечен невалидным (is_hotel_valid == False).
        """
        has_existing_data = bool(state.recommendations) or bool(state.cart.selected_bundle_id)
        return (
            has_existing_data
            and state.cart.is_transport_valid
            and not state.cart.is_hotel_valid
        )

    def handle_surgical_rebuild_node(self, state: AgentState) -> AgentState:
        """Заменяет только отель в уже найденных бандлах, сохраняя рейсы и даты."""
        pet_flag = bool(state.slots.pet_friendly.value) if state.slots.pet_friendly.status != SlotStatus.NO else False
        stars_val = state.slots.stars.value if isinstance(state.slots.stars.value, int) else None

        updated_recommendations: List[Dict[str, Any]] = []
        for bundle_dict in state.recommendations:
            bundle_obj = Bundle.model_validate(bundle_dict)
            rebuilt_bundle = self.tools.replace_hotel_only(
                current_bundle=bundle_obj,
                pet_friendly=pet_flag,
                stars=stars_val
            )
            updated_recommendations.append(rebuilt_bundle.model_dump())

        state.recommendations = updated_recommendations

        if state.cart.selected_bundle_id and updated_recommendations:
            selected = next(
                (b for b in updated_recommendations if b["bundle_id"] == state.cart.selected_bundle_id),
                updated_recommendations[0]
            )
            state.cart.hotel_data = selected["hotel"]

        state.cart.is_hotel_valid = True
        state.applied_heuristics.append(
            "Выполнена точечная пересборка (Surgical Invalidation): обновлён только отель, билеты сохранены."
        )
        state.current_step = StepStatus.BUNDLES_READY
        return state

    # =========================================================================
    # 4. TOOL CALLING & CONSTRAINT RELAXATION (Поиск и разрешение конфликтов)
    # =========================================================================
    def execute_search_node(self, state: AgentState) -> AgentState:
        """Вызывает поиск бандлов или генерирует 3 компромисса при нехватке бюджета."""
        slots = state.slots
        budget_int = slots.budget.value if isinstance(slots.budget.value, int) else None
        pet_flag = bool(slots.pet_friendly.value) if slots.pet_friendly.status != SlotStatus.NO else False
        stars_int = slots.stars.value if isinstance(slots.stars.value, int) else None
        transport_str = str(slots.transport.value) if slots.transport.value else None

        bundles = self.tools.get_trip_bundles(
            origin=str(slots.origin.value),
            destination=str(slots.destination.value),
            dates=str(slots.dates.value),
            budget=budget_int,
            guests=str(slots.guests.value) if slots.guests.value else None,
            pet_friendly=pet_flag,
            stars=stars_int,
            transport_type=transport_str
        )

        if not bundles and budget_int is not None:
            state.has_conflict = True
            state.conflict_reason = (
                f"По направлению '{slots.destination.value}' на даты '{slots.dates.value}' "
                f"нет готовых туров в пределах {budget_int} ₽. Предлагаем 3 компромиссных решения."
            )
            state.current_step = StepStatus.CONFLICT_DETECTED

            compromises = self.tools.get_conflict_compromises(
                origin=str(slots.origin.value),
                destination=str(slots.destination.value),
                dates=str(slots.dates.value),
                target_budget=budget_int,
                pet_friendly=pet_flag
            )
            state.recommendations = [c.model_dump() for c in compromises]
            return state

        state.has_conflict = False
        state.conflict_reason = None
        state.recommendations = [b.model_dump() for b in bundles]
        state.cart.is_transport_valid = True
        state.cart.is_hotel_valid = True
        state.current_step = StepStatus.BUNDLES_READY
        return state

    # =========================================================================
    # 5. СБОРКА КОРЗИНЫ
    # =========================================================================
    def select_bundle(self, state: AgentState, bundle_id: str) -> AgentState:
        """Фиксирует выбранный тур в ActiveCart."""
        chosen = next(
            (b for b in state.recommendations if b["bundle_id"] == bundle_id),
            state.recommendations[0] if state.recommendations else None
        )
        if chosen:
            state.cart.selected_bundle_id = chosen["bundle_id"]
            state.cart.transport_data = chosen["transport"]
            state.cart.hotel_data = chosen["hotel"]
            state.cart.transfer_data = chosen["transfer"]
            state.cart.is_transport_valid = True
            state.cart.is_hotel_valid = True
            state.current_step = StepStatus.TOUR_ASSEMBLED
        return state

    # =========================================================================
    # 6. POST-BOOKING SCENARIOS (Сценарии после покупки)
    # =========================================================================
    def _ensure_cart_populated(self, state: AgentState) -> None:
        if not state.cart.selected_bundle_id and state.recommendations:
            first_id = state.recommendations[0].get("bundle_id", "bundle_1")
            self.select_bundle(state, first_id)

    def handle_post_booking_node(self, state: AgentState, user_request: str) -> Optional[Dict[str, Any]]:
        has_active_trip = bool(state.cart.selected_bundle_id) or bool(state.recommendations)
        if not has_active_trip or not user_request:
            return None

        text_l = user_request.lower()
        self._ensure_cart_populated(state)

        hotel = state.cart.hotel_data or {}
        transport = state.cart.transport_data or {}
        transfer = state.cart.transfer_data or {}

        hotel_name = hotel.get("hotel_name", "выбранный отель")
        check_in = hotel.get("check_in_time", "14:00")
        carrier = transport.get("carrier", "Аэрофлот")
        dep_time = transport.get("departure_time", "07:45")
        arr_time = transport.get("arrival_time", "12:30")

        result: Optional[Dict[str, Any]] = None

        # Ранний заезд
        if any(w in text_l for w in ["ранний заезд", "заселиться раньше", "пораньше", "early check", "до 14:00"]):
            hotel["early_checkin_requested"] = True
            hotel["early_checkin_note"] = f"Запрос под прилёт в {arr_time} (стандартный заезд в {check_in})"
            state.cart.hotel_data = hotel

            msg = (
                f"Официальный запрос на ранний заезд (Early Check-in) отправлен в отель «{hotel_name}». "
                f"Ваш рейс ({carrier}) прибывает в {arr_time}, номер постараются подготовить к 13:30."
            )
            result = {"action_type": "early_checkin", "status": "confirmed", "hotel_name": hotel_name, "message": msg}

        # Трансфер
        elif any(w in text_l for w in ["трансфер", "такси", "встретить в аэропорту", "доехать до отеля"]):
            transfer["type"] = "Индивидуальный трансфер (встреча с табличкой)"
            transfer["price"] = 3500
            transfer["compatibility_note"] = f"Водитель отслеживает рейс {carrier} (прилёт в {arr_time})."
            state.cart.transfer_data = transfer

            msg = f"К бронированию в «{hotel_name}» привязан трансфер под рейс {carrier} (прилёт в {arr_time})."
            result = {"action_type": "transfer_booking", "status": "synchronized", "hotel_name": hotel_name, "message": msg}

        # Перенос дат
        elif any(w in text_l for w in ["позже", "раньше на", "перенести дат", "изменить дат", "сдвинуть дат"]):
            shift_days = 2
            digits = re.findall(r"\d+", text_l)
            if digits:
                shift_days = int(digits[0])
            new_dates_str = f"{state.slots.dates.value or 'ноябрь'} (сдвиг на {shift_days} дн.)"
            state.slots.dates = Slot(value=new_dates_str, status=SlotStatus.YES, raw_text=user_request)
            hotel["dates_modified"] = new_dates_str
            state.cart.hotel_data = hotel

            msg = f"Даты поездки в «{hotel_name}» перенесены на: {new_dates_str}."
            result = {"action_type": "date_modification", "status": "rescheduled", "message": msg}

        # Напоминания
        elif any(w in text_l for w in ["напоминан", "напомни", "уведомлен", "регистрация"]):
            reminders = [
                f"За 24 часа до вылета ({dep_time}): открытие онлайн-регистрации на рейс {carrier}.",
                f"За 3 часа: выезд в аэропорт.",
                f"К {check_in}: готовность номера в отеле «{hotel_name}»."
            ]
            transport["reminders"] = reminders
            state.cart.transport_data = transport
            result = {"action_type": "trip_reminders", "status": "scheduled", "message": "Напоминания активированы."}

        if result is not None:
            self.last_post_booking_result = result
            state.applied_heuristics.append(f"[Post-Booking] {result['message']}")
            state.current_step = StepStatus.TOUR_ASSEMBLED
            return result

        return None

    # =========================================================================
    # 7. ГЛАВНЫЙ ЦИКЛ ОРХЕСТРАЦИИ (ДЕЛЬТА СЛОТОВ)
    # =========================================================================
    def run(
        self,
        state: AgentState,
        incoming_slots: Optional[TravelSlots] = None,
        user_request: Optional[str] = None
    ) -> AgentState:
        """Внутренняя точка входа графа состояний (принимает уже распарсенные слоты)."""
        if user_request and self.handle_post_booking_node(state, user_request):
            return state

        if incoming_slots is not None:
            state.update_slots(incoming_slots)

        if self.can_do_surgical_hotel_rebuild(state):
            return self.handle_surgical_rebuild_node(state)

        state = self.check_blockers_node(state)
        if state.current_step == StepStatus.WAIT_USER_INPUT:
            return state

        state = self.resolve_vague_slots_node(state)
        state = self.execute_search_node(state)
        return state

    # =========================================================================
    # 8. ЧЕЛОВЕЧЕСКИЙ ВХОД ДЛЯ ЖИВОГО ТЕКСТА (СВЯЗКА С LLM)
    # =========================================================================
    def process_user_message(self, user_text: str, state: AgentState, *, generate_details: bool = True) -> AgentState:
        """
        Основной метод для чата/Streamlit:
        Принимает живой текст -> парсит через LLMClient -> запускает run().
        """
        # Сначала проверяем пост-букинг
        if (state.cart.selected_bundle_id or state.recommendations) and self.handle_post_booking_node(state, user_text):
            return state

        # NLU-парсинг через Qwen
        incoming_slots = self.llm.extract_slots(user_message=user_text, state=state)

        # Вызов State Machine
        state = self.run(state, incoming_slots=incoming_slots, user_request=user_text)

        # HTTP renders its own grounded answer; avoid redundant model generations.
        if not generate_details:
            return state

        # Генерация уточняющего вопроса через модель
        if state.current_step == StepStatus.WAIT_USER_INPUT:
            missing = []
            if state.slots.origin.status == SlotStatus.NO:
                missing.append("origin")
            elif state.slots.dates.status == SlotStatus.NO:
                missing.append("month")
            else:
                missing.append("activity")
            state.clarification_question = self.llm.generate_clarification_question(missing, state)

        # Генерация блоков Explainability через модель
        elif state.current_step == StepStatus.BUNDLES_READY:
            self.llm.enrich_bundles_with_explanations(state)

        return state


if __name__ == "__main__":
    wf = AgentWorkflow()
    st = AgentState()

    st = wf.process_user_message("Хочу к морю в ноябре недорого", st)
    print("Шаг 1 (Блокер):", st.clarification_question)

    st = wf.process_user_message("Из Москвы", st)
    print("Шаг 2 (Статус):", st.current_step.value)
    if st.recommendations:
        print("Отель:", st.recommendations[0]["hotel"]["hotel_name"], "| Цена:", st.recommendations[0]["price_total"])

    st = wf.process_user_message("А с нами ещё поедет собака", st)
    if st.recommendations:
        print("Шаг 3 (Собака):", st.recommendations[0]["hotel"]["hotel_name"], "| Цена:", st.recommendations[0]["price_total"])