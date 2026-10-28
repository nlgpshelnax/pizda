from enum import Enum
from typing import Optional, Any, List, Dict
from pydantic import BaseModel, Field


class SlotStatus(str, Enum):
    """Трехзначная логика состояния слота."""
    YES = "YES"        # Параметр четко указан пользователем ("из Москвы", "15 ноября")
    VAGUE = "VAGUE"    # Параметр размыт, нужна эвристика ("недорого", "к теплому морю", "осенью")
    NO = "NO"          # Параметр вообще не упоминался в диалоге


class StepStatus(str, Enum):
    """Этапы конечного автомата (State Machine)."""
    INIT = "init"
    WAIT_USER_INPUT = "wait_user_input"      # Сработал Blocker, ждем ответ на 1 вопрос
    BLOCKERS_PASSED = "blockers_passed"      # Обязательное трио собрано
    VAGUE_RESOLVED = "vague_resolved"        # Эвристики применены
    CONFLICT_DETECTED = "conflict_detected"  # Конфликт бюджета/условий (нужны 3-5 альтернатив)
    BUNDLES_READY = "bundles_ready"          # Топ вариантов сформирован
    TOUR_ASSEMBLED = "tour_assembled"        # Пользователь выбрал вариант (корзина собрана)


class Slot(BaseModel):
    """Единичный параметр запроса."""
    value: Optional[Any] = Field(default=None, description="Извлеченное значение параметра")
    status: SlotStatus = Field(default=SlotStatus.NO, description="Статус определенности: YES, VAGUE, NO")
    raw_text: Optional[str] = Field(default=None, description="Исходная фраза пользователя для этого слота")


class TravelSlots(BaseModel):
    """
    КОНТРАКТ ДЛЯ ПРОМПТ-ИНЖЕНЕРА:
    Схема, которую LLM заполняет при парсинге сообщения пользователя.
    """
    # Обязательное трио для Blocker Algorithm (origin + dates + [destination OR vibe])
    origin: Slot = Field(default_factory=Slot, description="Город отправления (откуда)")
    dates: Slot = Field(default_factory=Slot, description="Даты поездки, месяц или сезон (когда)")
    destination: Slot = Field(default_factory=Slot, description="Конкретная страна или город (куда)")
    vibe: Slot = Field(default_factory=Slot, description="Формат отдыха / настроение (море, горы, экскурсии)")

    # Дополнительные параметры фильтрации и баз данных
    budget: Slot = Field(default_factory=Slot, description="Бюджет поездки (число или 'недорого'/'люкс')")
    guests: Slot = Field(default_factory=Slot, description="Состав гостей (взрослые, дети)")
    pet_friendly: Slot = Field(default_factory=Slot, description="Наличие домашних животных")
    stars: Slot = Field(default_factory=Slot, description="Желаемая категория отеля (3*, 4*, 5*)")
    visa: Slot = Field(default_factory=Slot, description="Ограничения по визе (без визы / есть шенген)")
    transport: Slot = Field(default_factory=Slot, description="Предпочтения по транспорту (самолет, поезд, авто)")


class ActiveCart(BaseModel):
    """
    Состояние собранного тура для точечной пересборки (Surgical Invalidation).
    Позволяет сбрасывать только отель при изменении pet_friendly/stars, сохраняя билеты.
    """
    selected_bundle_id: Optional[str] = None
    transport_data: Optional[Dict[str, Any]] = None
    hotel_data: Optional[Dict[str, Any]] = None
    transfer_data: Optional[Dict[str, Any]] = None

    # Флаги актуальности компонентов
    is_transport_valid: bool = True
    is_hotel_valid: bool = True


class AgentState(BaseModel):
    """
    ГЛАВНЫЙ БЛОКНОТ АГЕНТА (State Machine).
    Передается между узлами графа в workflow.py и отдается на Frontend.
    """
    session_id: str = Field(default="default-session")
    slots: TravelSlots = Field(default_factory=TravelSlots)

    # Управление пайплайном
    current_step: StepStatus = Field(default=StepStatus.INIT)
    clarification_question: Optional[str] = Field(
        default=None,
        description="Единственный вопрос от Blocker Algorithm"
    )

    # Логика эвристик и конфликтов
    applied_heuristics: List[str] = Field(
        default_factory=list,
        description="Какие размытые слоты агент додумал сам (для прозрачности)"
    )
    has_conflict: bool = Field(default=False, description="Флаг конфликта (например, нехватка бюджета)")
    conflict_reason: Optional[str] = Field(default=None, description="Причина конфликта")

    # Выдача для пользователя и корзина
    recommendations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Топ-3/5 собранных бандлов с блоком Explainability"
    )
    cart: ActiveCart = Field(default_factory=ActiveCart)

    # Метрики качества агента (требование хакатона: <= 2 уточнений)
    clarification_count: int = Field(default=0, description="Счетчик заданных уточняющих вопросов")
    history_messages: List[Dict[str, str]] = Field(default_factory=list)

    def update_slots(self, new_slots: TravelSlots) -> List[str]:
        """
        Обновляет только те слоты, которые пришли в новом сообщении пользователя,
        и автоматически помечает, какие части корзины нужно пересобрать (Surgical Invalidation).
        Возвращает список измененных полей.
        """
        changed_fields: List[str] = []

        for field_name in TravelSlots.model_fields.keys():
            incoming_slot: Slot = getattr(new_slots, field_name)
            current_slot: Slot = getattr(self.slots, field_name)

            # Обновляем слот, только если в новом сообщении он не пустой (не NO)
            if incoming_slot.status != SlotStatus.NO and incoming_slot.value != current_slot.value:
                setattr(self.slots, field_name, incoming_slot)
                changed_fields.append(field_name)

        # Логика точечной инвалидации (Surgical Invalidation):
        # 1. Если изменились параметры только отеля (питомцы, звезды) — билеты НЕ сбрасываем
        hotel_only_triggers = {"pet_friendly", "stars"}
        # 2. Если изменились локация, даты или состав гостей — пересобираем и транспорт, и отель
        full_rebuild_triggers = {"origin", "destination", "dates", "guests", "transport"}

        if any(field in full_rebuild_triggers for field in changed_fields):
            self.cart.is_transport_valid = False
            self.cart.is_hotel_valid = False
        elif any(field in hotel_only_triggers for field in changed_fields):
            self.cart.is_hotel_valid = False
            # is_transport_valid остается True!

        return changed_fields

    def to_frontend_badges(self) -> Dict[str, Dict[str, Any]]:
        """
        КОНТРАКТ ДЛЯ ФРОНТЕНДЕРА:
        Отдает компактный словарь слотов для отрисовки цветных бейджей в UI.
        """
        return {
            name: {
                "value": getattr(self.slots, name).value,
                "status": getattr(self.slots, name).status.value
            }
            for name in TravelSlots.model_fields.keys()
        }


if __name__ == "__main__":
    # Быстрый локальный тест файла state.py
    state = AgentState()

    # 1. Имитируем первый запрос: "Хочу покупаться в ноябре недорого из Москвы"
    first_input = TravelSlots(
        origin=Slot(value="Москва", status=SlotStatus.YES),
        dates=Slot(value="ноябрь", status=SlotStatus.YES),
        vibe=Slot(value="покупаться / теплое море", status=SlotStatus.VAGUE),
        budget=Slot(value="недорого", status=SlotStatus.VAGUE),
    )
    changed = state.update_slots(first_input)
    print("Измененные слоты после 1-го сообщения:", changed)
    print("Бейджи для фронтенда:", state.to_frontend_badges())

    # 2. Имитируем, что тур собран, и пользователь пишет: "А с нами едет собака"
    state.cart.is_transport_valid = True
    state.cart.is_hotel_valid = True

    second_input = TravelSlots(
        pet_friendly=Slot(value=True, status=SlotStatus.YES, raw_text="с нами едет собака")
    )
    changed_after_dog = state.update_slots(second_input)
    print("\nИзмененные слоты после 2-го сообщения:", changed_after_dog)
    print(f"Статус корзины -> Билеты валидны: {state.cart.is_transport_valid}, Отель валиден: {state.cart.is_hotel_valid}")