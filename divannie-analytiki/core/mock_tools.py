from typing import Optional, List
from core.tools_interface import (
    DestinationSuggestion,
    TransportDetails,
    HotelDetails,
    TransferDetails,
    BundleExplanation,
    Bundle,
)


class MockTravelTools:
    """
    Синтетическая реализация инструментов для автономной разработки ядра
    и страховки (fallback) на случай сбоев внешних API во время демо.
    """

    def search_destinations(
        self,
        vibe: str,
        month: str,
        visa_preference: Optional[str] = None
    ) -> List[DestinationSuggestion]:
        vibe_l = vibe.lower()
        month_l = month.lower()

        # Сценарий 1: Тёплое море / покупаться осенью-зимой
        if any(w in vibe_l for w in ["мор", "пляж", "купат", "тепл"]):
            suggestions = [
                DestinationSuggestion(
                    destination="Египет (Шарм-эш-Шейх)",
                    visa_required=False,
                    visa_info="Без визы (бесплатный Синайский штамп по прилете до 15 дней)",
                    weather_summary=f"В период '{month}' воздух +28°C, вода +26°C, солнечно",
                    flight_duration_hours=5.5,
                    estimated_min_budget=85000,
                    why_suits="Самое близкое тёплое море без виз с коротким прямым перелётом и системой All Inclusive."
                ),
                DestinationSuggestion(
                    destination="ОАЭ (Дубай / Рас-эль-Хайма)",
                    visa_required=False,
                    visa_info="Без визы до 90 дней (штамп по прилете)",
                    weather_summary=f"В период '{month}' воздух +30°C, вода +27°C, без осадков",
                    flight_duration_hours=5.0,
                    estimated_min_budget=115000,
                    why_suits="Идеальная погода, высокий сервис для отдыха с детьми и прямые рейсы."
                ),
                DestinationSuggestion(
                    destination="Италия (Сицилия / Рим)",
                    visa_required=True,
                    visa_info="Требуется шенгенская виза",
                    weather_summary=f"В период '{month}' воздух +22°C, комфортно для прогулок и побережья",
                    flight_duration_hours=8.5,
                    estimated_min_budget=145000,
                    why_suits="Европейский колорит, гастрономия и мягкий средиземноморский климат (вариант с визой)."
                ),
            ]
        # Сценарий 2: Горы / лыжи / природа
        elif any(w in vibe_l for w in ["гор", "лыж", "сноуборд", "природ"]):
            suggestions = [
                DestinationSuggestion(
                    destination="Сочи (Красная Поляна)",
                    visa_required=False,
                    visa_info="Внутренний рейс РФ (по российскому паспорту)",
                    weather_summary=f"В период '{month}' свежий горный воздух, трассы и спа-комплексы",
                    flight_duration_hours=3.5,
                    estimated_min_budget=60000,
                    why_suits="Доступно на самолёте или поезде, развитая инфраструктура, много pet-friendly отелей."
                ),
                DestinationSuggestion(
                    destination="Турция (Улудаг / Каппадокия)",
                    visa_required=False,
                    visa_info="Без визы до 60 дней",
                    weather_summary=f"В период '{month}' солнечная горная погода, +10..+15°C",
                    flight_duration_hours=4.5,
                    estimated_min_budget=95000,
                    why_suits="Живописные панорамы и отели с подогреваемыми бассейнами без визовых формальностей."
                ),
            ]
        # Универсальный сценарий (экскурсии / города)
        else:
            suggestions = [
                DestinationSuggestion(
                    destination="Турция (Стамбул)",
                    visa_required=False,
                    visa_info="Без визы до 60 дней",
                    weather_summary=f"В период '{month}' +18°C, комфортно для экскурсий",
                    flight_duration_hours=4.5,
                    estimated_min_budget=75000,
                    why_suits="Богатая архитектура, прямые вылеты и отсутствие визы."
                ),
                DestinationSuggestion(
                    destination="Франция (Париж)",
                    visa_required=True,
                    visa_info="Требуется шенгенская виза",
                    weather_summary=f"В период '{month}' +16°C, переменная облачность",
                    flight_duration_hours=8.0,
                    estimated_min_budget=155000,
                    why_suits="Классический экскурсионный маршрут с мировыми музеями (вариант с визой)."
                ),
            ]

        # Если пользователь строго попросил "без визы"
        if visa_preference and "без" in visa_preference.lower():
            suggestions = [s for s in suggestions if not s.visa_required]

        return suggestions

    def get_trip_bundles(
        self,
        origin: str,
        destination: str,
        dates: str,
        budget: Optional[int] = None,
        guests: Optional[str] = None,
        pet_friendly: bool = False,
        stars: Optional[int] = None,
        transport_type: Optional[str] = None
    ) -> List[Bundle]:
        t_type = transport_type or "plane"
        is_visa_dest = any(c in destination.lower() for c in ["итал", "франц", "герман", "испан"])

        # Базовые варианты отелей и перелетов
        bundles = [
            Bundle(
                bundle_id="bundle-opt-1",
                destination=destination,
                dates=dates,
                visa_required=is_visa_dest,
                weather_forecast="Солнечно, воздух +27°C, море +25°C",
                price_total=88000,
                transport=TransportDetails(
                    transport_type=t_type,
                    carrier="Аэрофлот (прямой рейс)" if t_type == "plane" else "РЖД Фирменный",
                    origin=origin,
                    destination=destination,
                    departure_time="07:45",
                    arrival_time="12:30",
                    duration_hours=4.75,
                    is_direct=True,
                    price_rub=36000
                ),
                hotel=HotelDetails(
                    hotel_name="Coral Sun Family Resort 4*" if not pet_friendly else "Green Paw Oasis Hotel 4*",
                    stars=stars or 4,
                    location_note="Вторая береговая линия (6 минут пешком по парку до пляжа)",
                    meal_plan="All Inclusive (Всё включено)",
                    cancellation_policy="Бесплатная отмена за 7 дней до заезда",
                    pet_friendly=pet_friendly,
                    check_in_time="14:00",
                    price_rub=52000
                ),
                transfer=TransferDetails(
                    included=True,
                    transfer_type="Групповой комфортабельный шаттл",
                    duration_minutes=40,
                    price_rub=0,
                    schedule_compatible=True,
                    compatibility_note="Прилёт в 12:30 + 40 мин трансфер = вы в отеле к 13:40, ровно к началу заселения в 14:00."
                ),
                explanation=BundleExplanation(
                    why="Идеальный баланс цены и качества: утренний прямой перелёт без потери дня, питание 'всё включено' и бесплатная отмена.",
                    tradeoffs="Отель находится на второй линии (около 450 метров до пляжа), трансфер групповой.",
                    risks="Осталось мало номеров по невозвратному тарифу авиакомпании; в обед возможен ветер на пирсе."
                )
            ),
            Bundle(
                bundle_id="bundle-comfort-2",
                destination=destination,
                dates=dates,
                visa_required=is_visa_dest,
                weather_forecast="Солнечно, воздух +27°C, море +25°C",
                price_total=112000,
                transport=TransportDetails(
                    transport_type=t_type,
                    carrier="Аэрофлот (прямой рейс)",
                    origin=origin,
                    destination=destination,
                    departure_time="10:15",
                    arrival_time="15:00",
                    duration_hours=4.75,
                    is_direct=True,
                    price_rub=40000
                ),
                hotel=HotelDetails(
                    hotel_name="Grand Azure Palace 5*",
                    stars=5,
                    location_note="Первая береговая линия, собственный песчаный пляж",
                    meal_plan="Ultra All Inclusive",
                    cancellation_policy="Бесплатная отмена за 3 дня до заезда",
                    pet_friendly=pet_friendly,
                    check_in_time="14:00",
                    price_rub=67000
                ),
                transfer=TransferDetails(
                    included=True,
                    transfer_type="Индивидуальный трансфер с табличкой",
                    duration_minutes=25,
                    price_rub=5000,
                    schedule_compatible=True,
                    compatibility_note="Прилёт в 15:00 + 25 мин индивидуальный трансфер = мгновенное заселение в номер без ожидания на ресепшене."
                ),
                explanation=BundleExplanation(
                    why="Максимальный комфорт: первая линия с пологим песчаным входом, индивидуальный трансфер и гибкая отмена.",
                    tradeoffs="Стоимость выше базового эконом-сегмента на 24 000 ₽.",
                    risks="При размещении с питомцем отель просит депозит 50$ при заезде." if pet_friendly else "Популярный семейный отель — высокая заполняемость у главного бассейна."
                )
            ),
        ]

        # Если задан жесткий численный бюджет, фильтруем подходящие
        if isinstance(budget, int):
            matching = [b for b in bundles if b.price_total <= budget]
            return matching  # Если вернется пустой список [], workflow запустит get_conflict_compromises()

        return bundles

    def get_conflict_compromises(
        self,
        origin: str,
        destination: str,
        dates: str,
        target_budget: int,
        pet_friendly: bool = False
    ) -> List[Bundle]:
        """
        Constraint Relaxation: генерирует 3 компромиссных варианта,
        когда базовые туры не помещаются в target_budget пользователя.
        """
        base_bundle = self.get_trip_bundles(origin, destination, dates, pet_friendly=pet_friendly)[0]

        # Альтернатива 1: Сдвиг дат на 3 дня (дешевле перелет)
        alt_shift_dates = base_bundle.model_copy(deep=True)
        alt_shift_dates.bundle_id = "comp-shift-dates"
        alt_shift_dates.dates = f"{dates} (сдвиг вылета на +3 дня, вторник)"
        alt_shift_dates.price_total = target_budget - 2000
        alt_shift_dates.is_compromise = True
        alt_shift_dates.compromise_type = "shift_dates"
        alt_shift_dates.explanation = BundleExplanation(
            why=f"Укладывается в ваш бюджет ({alt_shift_dates.price_total} ₽) с сохранением отеля 4* и прямого перелёта.",
            tradeoffs="Пришлось сдвинуть дату вылета на 3 дня вперёд (вылет во вторник дешевле выходных).",
            risks="Нужно согласовать сдвиг дат отпуска."
        )

        # Альтернатива 2: Отель попроще (3* на завтраках вместо 4* All Inclusive)
        alt_simpler_hotel = base_bundle.model_copy(deep=True)
        alt_simpler_hotel.bundle_id = "comp-simpler-hotel"
        alt_simpler_hotel.price_total = target_budget - 4500
        alt_simpler_hotel.hotel.hotel_name = "City & Sea ApartHotel 3*"
        alt_simpler_hotel.hotel.stars = 3
        alt_simpler_hotel.hotel.meal_plan = "BB (Только завтраки)"
        alt_simpler_hotel.is_compromise = True
        alt_simpler_hotel.compromise_type = "simpler_hotel"
        alt_simpler_hotel.explanation = BundleExplanation(
            why=f"Сохранены ваши точные даты ({dates}) и прямой перелёт, цена ниже лимита ({alt_simpler_hotel.price_total} ₽).",
            tradeoffs="Отель 3* вместо 4*, включены только завтраки, до пляжа 12 минут пешком.",
            risks="Расходы на обеды и ужины в кафе потребуют отдельного бюджета на месте."
        )

        # Альтернатива 3: Чуть выше бюджета (зато без потерь в качестве)
        alt_over_budget = base_bundle.model_copy(deep=True)
        alt_over_budget.bundle_id = "comp-over-budget"
        alt_over_budget.is_compromise = True
        alt_over_budget.compromise_type = "over_budget"
        diff = alt_over_budget.price_total - target_budget
        alt_over_budget.explanation = BundleExplanation(
            why="Полностью сохраняет ваши даты, отель 4* 'Всё включено' и прямой утренний рейс.",
            tradeoffs=f"Превышает указанный бюджет на {diff} ₽ (итого {alt_over_budget.price_total} ₽).",
            risks="Цена зафиксирована на сегодня и может вырасти ближе к вылету."
        )

        return [alt_shift_dates, alt_simpler_hotel, alt_over_budget]

    def replace_hotel_only(
        self,
        current_bundle: Bundle,
        pet_friendly: bool = False,
        stars: Optional[int] = None
    ) -> Bundle:
        """
        Хирургическая пересборка: оставляет нетронутыми билеты (transport) и даты,
        но заменяет отель под новые условия (например, 'с нами собака').
        """
        updated = current_bundle.model_copy(deep=True)
        target_stars = stars or updated.hotel.stars

        if pet_friendly:
            updated.hotel.hotel_name = f"PetFriendly Pine & Sea Resort {target_stars}*"
            updated.hotel.pet_friendly = True
            updated.hotel.price_rub += 6000
            updated.price_total = updated.transport.price_rub + updated.hotel.price_rub + updated.transfer.price_rub
            updated.explanation.why = (
                f"Перелёт ({updated.transport.carrier}, {updated.transport.departure_time}) сохранён без изменений! "
                f"Отель заменён на pet-friendly вариант с территорией для выгула."
            )
            updated.explanation.tradeoffs = "Доплата за специализированный pet-friendly номер составила +6 000 ₽."
            updated.explanation.risks = "Не забудьте ветеринарный паспорт и переноску для перелёта."
        elif stars:
            updated.hotel.stars = stars
            updated.hotel.hotel_name = f"Selected Comfort Hotel {stars}*"
            price_delta = (stars - current_bundle.hotel.stars) * 12000
            updated.hotel.price_rub = max(25000, updated.hotel.price_rub + price_delta)
            updated.price_total = updated.transport.price_rub + updated.hotel.price_rub + updated.transfer.price_rub
            updated.explanation.why = f"Билеты и расписание сохранены. Отель обновлён до категории {stars}*."

        return updated


if __name__ == "__main__":
    tools = MockTravelTools()

    print("=== 1. Тест подбора направлений (с визой и без) ===")
    dests = tools.search_destinations(vibe="теплое море", month="ноябрь")
    for d in dests:
        visa_tag = "Виза нужна" if d.visa_required else "Без визы"
        print(f"- {d.destination} [{visa_tag}]: {d.weather_summary} | от {d.estimated_min_budget} ₽")

    print("\n=== 2. Тест сборки бандла и проверки стыковок ===")
    bundles = tools.get_trip_bundles(origin="Москва", destination="Египет (Шарм-эш-Шейх)", dates="10-17 ноября")
    b0 = bundles[0]
    print(f"Тур: {b0.hotel.hotel_name}, Итого: {b0.price_total} ₽")
    print(f"Стыковка: {b0.transfer.compatibility_note}")

    print("\n=== 3. Тест хирургической пересборки (добавили собаку) ===")
    rebuilt = tools.replace_hotel_only(b0, pet_friendly=True)
    print(f"Новый отель: {rebuilt.hotel.hotel_name} (pet_friendly={rebuilt.hotel.pet_friendly})")
    print(f"Рейс остался прежним: {rebuilt.transport.carrier}, вылет {rebuilt.transport.departure_time}")
    print(f"Объяснение: {rebuilt.explanation.why}")

    print("\n=== 4. Тест разрешения конфликта (бюджет 65 000 ₽) ===")
    compromises = tools.get_conflict_compromises(
        origin="Москва", destination="Египет (Шарм-эш-Шейх)", dates="10-17 ноября", target_budget=65000
    )
    for c in compromises:
        print(f"- [{c.compromise_type}] {c.price_total} ₽ -> Компромисс: {c.explanation.tradeoffs}")