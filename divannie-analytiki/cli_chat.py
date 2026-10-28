import sys
from core.state import AgentState, StepStatus, SlotStatus
from core.workflow import AgentWorkflow
# Вместо BackendTravelTools:
from core.local_db_tools import LocalDBTravelTools



def print_slots_bar(state: AgentState) -> None:
    """Выводит текущее состояние слотов (YES / VAGUE / NO) в компактном виде."""
    slots_map = {
        "Откуда": state.slots.origin,
        "Куда": state.slots.destination,
        "Даты": state.slots.dates,
        "Вайб": state.slots.vibe,
        "Бюджет": state.slots.budget,
        "Гости": state.slots.guests,
        "Питомцы": state.slots.pet_friendly,
        "Звёзды": state.slots.stars,
    }
    parts = []
    for name, slot in slots_map.items():
        if slot.status == SlotStatus.YES:
            parts.append(f"🟢 {name}: {slot.value}")
        elif slot.status == SlotStatus.VAGUE:
            parts.append(f"🟡 {name}: {slot.value} (VAGUE)")
        else:
            parts.append(f"⚪ {name}: —")
    print("\n📊 СЛОТЫ: " + " | ".join(parts))


def print_bundles(recommendations: list) -> None:
    """Форматированный вывод карточек туров строго по схеме tools_interface.py."""
    for idx, b in enumerate(recommendations, 1):
        transport = b.get("transport", {})
        hotel = b.get("hotel", {})
        transfer = b.get("transfer", {})
        expl = b.get("explanation", {})

        compromise_badge = ""
        if b.get("is_compromise"):
            compromise_badge = f" [КОМПРОМИСС: {b.get('compromise_type')}]"

        visa_str = "Нужна виза" if b.get("visa_required") else "Без визы"
        pet_str = "Да 🐾" if hotel.get("pet_friendly", hotel.get("pets_allowed")) else "Нет"
        t_price = transport.get("price_rub", transport.get("price", 0))
        h_price = hotel.get("price_rub", hotel.get("total_price", 0))

        print("\n" + "─" * 70)
        print(
            f"📦 ВАРИАНТ #{idx}{compromise_badge}: {b.get('destination')} "
            f"| ИТОГО: {b.get('price_total', 0):,} ₽"
        )
        print(f"🌤 Погода: {b.get('weather_forecast', 'Комфортная')} | 🛂 {visa_str}")
        print("─" * 70)

        print(
            f"✈️  Транспорт : {transport.get('carrier')} ({transport.get('origin')} ➔ {transport.get('destination')}) "
            f"| {transport.get('departure_time')} – {transport.get('arrival_time')} "
            f"({transport.get('duration_hours')} ч) | {t_price:,} ₽"
        )
        print(
            f"🏨 Отель     : {hotel.get('hotel_name')} ({hotel.get('stars')}★) "
            f"| {hotel.get('location_note', 'Удобное расположение')}"
        )
        print(
            f"🍽  Условия   : {hotel.get('meal_plan')} | Заезд с {hotel.get('check_in_time', '14:00')} "
            f"| С животными: {pet_str} | {h_price:,} ₽"
        )
        print(
            f"🚐 Трансфер  : {transfer.get('transfer_type', transfer.get('type'))} ({transfer.get('duration_minutes')} мин) "
            f"➔ {transfer.get('compatibility_note')}"
        )
        print(f"💡 Почему подходит : {expl.get('why')}")
        print(f"⚖️  Компромиссы     : {expl.get('tradeoffs')}")
        print(f"⚠️  Риски           : {expl.get('risks')}")
    print("─" * 70)


def main():
    print("=" * 70)
    print("🏖️  AI-АГЕНТ «ОСТРОВОК» — КОНСОЛЬНЫЙ РЕЖИМ (CLI)")
    print("=" * 70)
    print("Команды управления:")
    print("  • Обычный текст   — диалог с агентом (поиск, уточнения, пересборка)")
    print("  • /select 1       — выбрать вариант №1 в корзину для пост-букинга")
    print("  • /slots          — показать детальную таблицу слотов и эвристик")
    print("  • /reset          — сбросить диалог и начать заново")
    print("  • exit / quit     — выход")
    print("=" * 70)

    # ✅ ДОЛЖНО БЫТЬ:
    tools = LocalDBTravelTools()
    workflow = AgentWorkflow(tools=tools)
    state = AgentState()

    while True:
        try:
            user_input = input("\n🧑 Вы: ").strip()
            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ("exit", "quit", "/exit", "/quit"):
                print("Завершение работы агента.")
                break

            if cmd == "/reset":
                state = AgentState()
                print("🔄 Сессия сброшена. Начните новый диалог!")
                continue

            if cmd == "/slots":
                print_slots_bar(state)
                if state.applied_heuristics:
                    print("⚙️ Применённые эвристики:")
                    for h in state.applied_heuristics:
                        print(f"   • {h}")
                continue

            if cmd.startswith("/select"):
                parts = cmd.split()
                idx = int(parts[1]) - 1 if len(parts) > 1 and parts[1].isdigit() else 0
                if state.recommendations and 0 <= idx < len(state.recommendations):
                    bundle_id = state.recommendations[idx]["bundle_id"]
                    state = workflow.select_bundle(state, bundle_id)
                    hotel_name = state.cart.hotel_data.get("hotel_name", "Отель")
                    print(
                        f"\n✅ Тур #{idx + 1} («{hotel_name}») зафиксирован в корзине!\n"
                        f"Теперь вы можете протестировать пост-букинг (например: 'Оформите ранний заезд' или 'Нужен трансфер')."
                    )
                else:
                    print("⚠️ Сначала найдите туры, чтобы выбрать вариант.")
                continue

            state = workflow.process_user_message(user_input, state)

            print_slots_bar(state)
            print(
                f"🧭 Шаг графа: [{state.current_step.value}] "
                f"| Уточнений задано: {state.clarification_count}/2 "
                f"| План в БД: {tools.last_plan_id or 'локальный'}"
            )

            if state.current_step == StepStatus.WAIT_USER_INPUT:
                print(f"\n🤖 Агент: {state.clarification_question}")
            elif state.current_step == StepStatus.BUNDLES_READY:
                print(f"\n🤖 Агент: Подобрал подходящие туры ({len(state.recommendations)} шт.):")
                print_bundles(state.recommendations)
                print("💬 Подсказка: напишите условие для пересборки (например, 'С нами едет собака') или '/select 1' для выбора тура.")
            elif state.current_step == StepStatus.CONFLICT_DETECTED:
                print(f"\n🤖 Агент (Разрешение конфликта): {state.conflict_reason}")
                print_bundles(state.recommendations)
            elif state.current_step == StepStatus.TOUR_ASSEMBLED:
                pb = workflow.last_post_booking_result
                if pb:
                    print(f"\n🛎️ Консьерж-сервис [{pb.get('action_type')}]: {pb.get('message')}")
                else:
                    print("\n🤖 Агент: Тур собран и находится в корзине.")

        except KeyboardInterrupt:
            print("\nВыход из программы.")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Ошибка выполнения: {e}")


if __name__ == "__main__":
    main()