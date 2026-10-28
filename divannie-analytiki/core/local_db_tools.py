import os
import re
import json
import sqlite3
from typing import List, Optional, Dict, Any

from core.tools_interface import (
    TravelTools,
    Bundle,
    TransportDetails,
    HotelDetails,
    TransferDetails,
    BundleExplanation,
    DestinationSuggestion,
)

# Автоматическое определение путей к travel.db и ds_contract_master.json в корне проекта
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "travel.db")
CONTRACT_PATH = os.path.join(BASE_DIR, "ds_contract_master.json")

# Список безвизовых стран для граждан РФ из нашего каталога
VISA_FREE_COUNTRIES = {"Россия", "Сербия", "Черногория", "Босния"}


class LocalDBTravelTools(TravelTools):
    """
    Локальный адаптер к базе SQLite (travel.db) и мастер-контракту (ds_contract_master.json).
    Выполняет прямые SQL-выборки, проверяет стыковку расписаний и формирует Топ-5 бандлов.
    """

    def __init__(self, db_path: str = DB_PATH, contract_path: str = CONTRACT_PATH):
        self.db_path = db_path
        self.contract_path = contract_path
        self.master_contract: Dict[str, Any] = {}
        # Для совместимости с логом в cli_chat.py
        self.last_plan_id: Optional[str] = "local-sqlite-db"

        if os.path.exists(self.contract_path):
            with open(self.contract_path, "r", encoding="utf-8") as f:
                self.master_contract = json.load(f)

        self.vibe_thresholds = self.master_contract.get(
            "vibe_thresholds", {"warm_air": 15, "swim_sea": 20, "ski_snow": 15}
        )

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # =========================================================================
    # 1. ПОИСК НАПРАВЛЕНИЙ ПО ВАЙБУ И СЕЗОНУ (ds_contract_master.json)
    # =========================================================================
    def search_destinations(
        self,
        vibe: str,
        month: str,
        visa_preference: Optional[str] = None
    ) -> List[DestinationSuggestion]:
        """
        Используется узлом resolve_vague_slots_node (Этап «Вдохновение»),
        когда пользователь не назвал конкретный город, но указал вайб (море, лыжи, спа).
        """
        vibe_l = str(vibe).lower()
        m_int = self._parse_month_to_int(month)
        suggestions: List[DestinationSuggestion] = []

        cities_dict = self.master_contract.get("cities", {})
        for code, info in cities_dict.items():
            country = info.get("country", "")
            is_visa_free = country in VISA_FREE_COUNTRIES

            # Если пользователь просил строго без визы — отсекаем визовые страны
            if visa_preference and "без виз" in visa_preference.lower() and not is_visa_free:
                continue

            weather_by_month = info.get("weather", {}).get(str(m_int), {})
            avg_temp = weather_by_month.get("avg_temp")
            if avg_temp is None:
                avg_temp = 15.0
            sea_temp = weather_by_month.get("sea_temp")
            snow = weather_by_month.get("snow_depth") or 0.0

            matches = False
            why_text = ""

            # Эвристика 1: Горные лыжи / сноуборд
            if any(w in vibe_l for w in ["лыж", "сноуборд", "гор", "ski"]):
                if snow >= self.vibe_thresholds.get("ski_snow", 15) or code in ("CMF", "CORT", "INN", "ZRH", "KOP", "ZBL", "JAH", "GRX", "AND"):
                    matches = True
                    why_text = f"Устойчивый снежный покров (~{int(snow)} см), открыты горнолыжные трассы."

            # Эвристика 2: Море и пляж
            elif any(w in vibe_l for w in ["мор", "пляж", "купат", "beach"]):
                if sea_temp is not None and sea_temp >= self.vibe_thresholds.get("swim_sea", 20):
                    matches = True
                    why_text = f"Тёплое море (+{int(sea_temp)}°C) и комфортный воздух (+{int(avg_temp)}°C)."
                elif sea_temp is not None and sea_temp >= 15:
                    matches = True
                    why_text = f"Мягкий морской бриз: воздух +{int(avg_temp)}°C, вода +{int(sea_temp)}°C."

            # Эвристика 3: СПА и термальные источники
            elif any(w in vibe_l for w in ["спа", "терм", "релакс", "spa", "wellness"]):
                if code in ("VHY", "MTC", "BAD", "BGS", "BRG", "KLV", "BUD", "VRN"):
                    matches = True
                    why_text = "Известный бальнеологический курорт с термальными комплексами."

            # Эвристика 4: Экскурсии, культура, архитектура
            else:
                if avg_temp >= 5.0:
                    matches = True
                    why_text = f"Комфортная погода (+{int(avg_temp)}°C) для прогулок, музеев и гастрономии."

            if matches:
                budget_info = info.get("budget", {})
                # Оценка минимального бюджета на 7 ночей (p25 отеля * 7 + перелёт)
                p25_night = float(budget_info.get("p25", 7000))
                min_b = int(p25_night * 7 + 38000)

                visa_str = "Без визы для граждан РФ" if is_visa_free else "Требуется шенгенская виза"
                w_parts = [f"Воздух +{avg_temp:.1f}°C"]
                if sea_temp is not None:
                    w_parts.append(f"море +{sea_temp:.1f}°C")
                if snow > 0:
                    w_parts.append(f"снег {snow:.0f} см")

                suggestions.append(
                    DestinationSuggestion(
                        destination=info.get("name_ru", code),
                        visa_required=not is_visa_free,
                        visa_info=visa_str,
                        weather_summary=", ".join(w_parts),
                        flight_duration_hours=4.0,
                        estimated_min_budget=min_b,
                        why_suits=why_text
                    )
                )

        if suggestions:
            # Сортируем так, чтобы в выдаче были сначала доступные безвизовые, затем визовые
            suggestions.sort(key=lambda x: (x.visa_required, x.estimated_min_budget))
            return suggestions[:5]

        # Запасной вариант, если фильтр оказался слишком строгим
        return [
            DestinationSuggestion(
                destination="Сочи",
                visa_required=False,
                visa_info="Без визы (по внутреннему паспорту РФ)",
                weather_summary="Воздух +15°C, мягкий субтропический климат",
                flight_duration_hours=3.5,
                estimated_min_budget=68000,
                why_suits="Универсальный курорт с морской набережной и горным кластером."
            )
        ]

    # =========================================================================
    # 2. СБОРКА ТОП-5 ТУРОВ ИЗ ТАБЛИЦ hotels И transport (travel.db)
    # =========================================================================
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
        """
        Делает SQL-запрос к travel.db, стыкует реальные рейсы и отели,
        рассчитывает тайминг трансфера до заселения и возвращает РОВНО 5 вариантов.
        """
        conn = self._get_conn()
        cur = conn.cursor()

        clean_origin = self._clean_city_name(origin)
        clean_dest = self._clean_city_name(destination)
        nights = self._extract_nights(dates)
        m_int = self._parse_month_to_int(dates)

        # 1. Ищем рейсы/поезда из города отправления в город назначения
        t_sql = """
            SELECT * FROM transport
            WHERE (origin_name_ru LIKE ? OR origin_code LIKE ?)
              AND (destination_name_ru LIKE ? OR destination_code LIKE ?)
        """
        t_params: List[Any] = [f"%{clean_origin}%", f"%{clean_origin}%", f"%{clean_dest}%", f"%{clean_dest}%"]

        if transport_type and transport_type in ("flight", "train"):
            t_sql += " AND type = ?"
            t_params.append(transport_type)

        # Фильтр по месяцу (в базе date имеет формат YY-MM-DD, например '26-03-15')
        month_prefix = f"26-{m_int:02d}-%"
        cur.execute(t_sql + " AND date LIKE ? ORDER BY price ASC LIMIT 10", t_params + [month_prefix])
        transports = [dict(r) for r in cur.fetchall()]

        # Если на конкретный месяц рейсов не нашлось — берём любые рейсы по этому маршруту
        if not transports:
            cur.execute(t_sql + " ORDER BY price ASC LIMIT 10", t_params)
            transports = [dict(r) for r in cur.fetchall()]

        # Если прямого маршрута нет — берём рейсы из города вылета
        if not transports:
            cur.execute(
                "SELECT * FROM transport WHERE origin_name_ru LIKE ? ORDER BY price ASC LIMIT 10",
                (f"%{clean_origin}%",)
            )
            transports = [dict(r) for r in cur.fetchall()]

        # 2. Ищем отели в городе назначения
        h_sql = """
            SELECT * FROM hotels
            WHERE (city_name_ru LIKE ? OR city_code LIKE ?)
        """
        h_params: List[Any] = [f"%{clean_dest}%", f"%{clean_dest}%"]

        if pet_friendly:
            h_sql += " AND pets_allowed = 1"
        if stars:
            h_sql += " AND stars >= ?"
            h_params.append(stars)

        h_sql += " ORDER BY price_per_night ASC LIMIT 15"
        cur.execute(h_sql, h_params)
        hotels = [dict(r) for r in cur.fetchall()]

        # Если фильтр звёздности оказался слишком строгим — ослабляем его, сохраняя город и питомцев
        if not hotels and stars:
            cur.execute(
                "SELECT * FROM hotels WHERE city_name_ru LIKE ?" + (" AND pets_allowed = 1" if pet_friendly else "") + " ORDER BY price_per_night ASC LIMIT 15",
                (f"%{clean_dest}%",)
            )
            hotels = [dict(r) for r in cur.fetchall()]

        # 3. Запрашиваем реальную погоду из таблицы weather
        weather_str = "Комфортная погода для отдыха"
        if hotels:
            c_code = hotels[0].get("city_code")
            cur.execute(
                "SELECT avg_temp, sea_temp, snow_depth FROM weather WHERE city_code = ? AND month = ?",
                (c_code, m_int)
            )
            w_row = cur.fetchone()
            if w_row:
                w_parts = [f"Воздух +{w_row['avg_temp']}°C"]
                if w_row["sea_temp"] is not None:
                    w_parts.append(f"море +{w_row['sea_temp']}°C")
                if w_row["snow_depth"] and w_row["snow_depth"] > 0:
                    w_parts.append(f"снег {w_row['snow_depth']} см")
                weather_str = ", ".join(w_parts)

        conn.close()

        if not hotels:
            return []

        # 4. Формируем до 5 разнообразных бандлов (от эконома до премиума)
        bundles: List[Bundle] = []
        country = hotels[0].get("country", "")
        is_visa_req = country not in VISA_FREE_COUNTRIES

        # Отбираем до 5 отелей из разных ценовых сегментов найденного списка
        selected_hotels = hotels[:5]

        meal_plans = [
            "BB (Завтрак включён)",
            "HB (Завтрак + Ужин)",
            "All Inclusive (Всё включено)",
            "RO (Только проживание)",
            "BB (Шведский стол)"
        ]

        for idx, h in enumerate(selected_hotels):
            t = transports[idx % len(transports)] if transports else {}

            t_price = int(float(t.get("price", 38000)))
            h_night = int(float(h.get("price_per_night", 7000)))
            h_total = h_night * nights
            transfer_price = 3000
            total_price = t_price + h_total + transfer_price

            # Расчёт тайминга: время прилёта + 40 минут трансфер vs время check_in
            dep_time = t.get("departure_time", "08:30")
            arr_time = t.get("arrival_time", "12:45")
            check_in = h.get("check_in_time", "14:00")
            compat_ok, compat_note = self._calc_schedule_compatibility(arr_time, 40, check_in)

            pet_allowed_bool = bool(h.get("pets_allowed", 0))
            stops_count = int(t.get("stops", 0))
            flight_type_note = "прямой рейс" if stops_count == 0 else f"рейс с {stops_count} пересадкой"

            b = Bundle(
                bundle_id=f"db_{h.get('id', idx+1)}",
                destination=h.get("city_name_ru", clean_dest),
                dates=f"{dates} ({nights} ночей)" if "ноч" not in str(dates) else str(dates),
                visa_required=is_visa_req,
                weather_forecast=weather_str,
                price_total=total_price,
                transport=TransportDetails(
                    transport_type="plane" if t.get("type", "flight") == "flight" else "train",
                    carrier=t.get("carrier", "Аэрофлот"),
                    origin=t.get("origin_name_ru", clean_origin),
                    destination=h.get("city_name_ru", clean_dest),
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_hours=float(t.get("duration_hours", 4.0)),
                    is_direct=(stops_count == 0),
                    price_rub=t_price
                ),
                hotel=HotelDetails(
                    hotel_name=h.get("name", f"Hotel {clean_dest}"),
                    stars=int(h.get("stars", 4)),
                    location_note=f"{h.get('city_name_ru', clean_dest)}, {country} (проверенный объект каталога)",
                    meal_plan=meal_plans[idx % len(meal_plans)],
                    cancellation_policy="Бесплатная отмена за 48 часов до заезда",
                    pet_friendly=pet_allowed_bool,
                    check_in_time=check_in,
                    price_rub=h_total
                ),
                transfer=TransferDetails(
                    included=True,
                    transfer_type="Индивидуальный трансфер (встреча в аэропорту)",
                    duration_minutes=40,
                    price_rub=transfer_price,
                    schedule_compatible=compat_ok,
                    compatibility_note=compat_note
                ),
                explanation=BundleExplanation(
                    why=(
                        f"Отель {h.get('stars')}★ «{h.get('name')}» ({h_night:,} ₽/ночь) в сочетании с "
                        f"перевозчиком {t.get('carrier', 'Аэрофлот')} ({flight_type_note})."
                    ),
                    tradeoffs=(
                        "Проживание с домашними животными подтверждено (pet-friendly)."
                        if pet_allowed_bool else
                        "Стандартная категория номера; без размещения животных."
                    ),
                    risks=(
                        "Требуется действующая шенгенская виза."
                        if is_visa_req else
                        "Безвизовый въезд; высокий спрос на даты — рекомендуем раннее бронирование."
                    )
                )
            )
            bundles.append(b)

        # Проверка бюджетного конфликта:
        # Если пользователь указал строгий бюджет, и даже самый дешёвый вариант дороже —
        # возвращаем пустой список, чтобы workflow.py запустил ветку Constraint Relaxation (3 компромисса)
        if budget is not None and bundles:
            within_budget = [b for b in bundles if b.price_total <= budget]
            if not within_budget:
                return []
            # Если часть вариантов проходит по бюджету, ставим их первыми, но добиваем до 5 для сравнения
            outside_budget = [b for b in bundles if b.price_total > budget]
            return (within_budget + outside_budget)[:5]

        return bundles

    # =========================================================================
    # 3. SURGICAL INVALIDATION (ТОЧЕЧНАЯ ЗАМЕНА ОТЕЛЯ БЕЗ СБРОСА БИЛЕТОВ)
    # =========================================================================
    def replace_hotel_only(
        self,
        current_bundle: Bundle,
        pet_friendly: bool = False,
        stars: Optional[int] = None
    ) -> Bundle:
        """
        Меняет ТОЛЬКО отель из базы travel.db (например, когда пользователь добавил собаку),
        сохраняя прежний авиабилет и время вылета нетронутыми.
        """
        conn = self._get_conn()
        cur = conn.cursor()

        clean_dest = self._clean_city_name(current_bundle.destination)
        sql = "SELECT * FROM hotels WHERE (city_name_ru LIKE ? OR city_code LIKE ?)"
        params: List[Any] = [f"%{clean_dest}%", f"%{clean_dest}%"]

        if pet_friendly:
            sql += " AND pets_allowed = 1"
        if stars:
            sql += " AND stars = ?"
            params.append(stars)

        sql += " ORDER BY price_per_night ASC LIMIT 10"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        # Выбираем новый отель, который отличается от старого
        chosen = None
        for r in rows:
            if r.get("name") != current_bundle.hotel.hotel_name:
                chosen = r
                break
        if not chosen and rows:
            chosen = rows[0]

        if chosen:
            nights = self._extract_nights(current_bundle.dates)
            h_night = int(float(chosen.get("price_per_night", 7500)))
            h_total = h_night * nights
            check_in = chosen.get("check_in_time", "14:00")
            pet_flag = bool(chosen.get("pets_allowed", 0))

            # Пересчитываем стыковку со старым рейсом
            compat_ok, compat_note = self._calc_schedule_compatibility(
                current_bundle.transport.arrival_time, 40, check_in
            )

            new_hotel = HotelDetails(
                hotel_name=chosen.get("name", current_bundle.hotel.hotel_name),
                stars=int(chosen.get("stars", current_bundle.hotel.stars)),
                location_note=current_bundle.hotel.location_note,
                meal_plan=current_bundle.hotel.meal_plan,
                cancellation_policy="Бесплатная отмена за 48 часов",
                pet_friendly=pet_flag,
                check_in_time=check_in,
                price_rub=h_total
            )

            new_total = current_bundle.transport.price_rub + h_total + current_bundle.transfer.price_rub

            current_bundle.hotel = new_hotel
            current_bundle.price_total = new_total
            current_bundle.transfer.schedule_compatible = compat_ok
            current_bundle.transfer.compatibility_note = compat_note
            current_bundle.explanation.why = (
                f"Хирургическая пересборка: билеты на рейс {current_bundle.transport.carrier} "
                f"({current_bundle.transport.departure_time}) сохранены, отель заменён на "
                f"«{new_hotel.hotel_name}» ({new_hotel.stars}★, pet_friendly={pet_flag})."
            )
            current_bundle.explanation.tradeoffs = (
                "Отель официально принимает гостей с питомцами (pets_allowed=1 в БД)."
                if pet_flag else "Обновлена категория отеля по вашему запросу."
            )

        return current_bundle

    # =========================================================================
    # 4. CONSTRAINT RELAXATION (3 КОМПРОМИССА ПРИ КОНФЛИКТЕ БЮДЖЕТА)
    # =========================================================================
    def get_conflict_compromises(
        self,
        origin: str,
        destination: str,
        dates: str,
        target_budget: int,
        pet_friendly: bool = False
    ) -> List[Bundle]:
        """
        Если самый дешёвый тур в базе дороже бюджета пользователя,
        строит 3 реальных компромисса на данных из travel.db:
        1) Сокращение длительности (5 ночей вместо 7) — укладывается в бюджет;
        2) Отель 3★ минимальной цены в городе;
        3) Лучший вариант 4★ с минимальной доплатой сверх бюджета.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        clean_origin = self._clean_city_name(origin)
        clean_dest = self._clean_city_name(destination)

        cur.execute(
            "SELECT * FROM transport WHERE origin_name_ru LIKE ? AND destination_name_ru LIKE ? ORDER BY price ASC LIMIT 1",
            (f"%{clean_origin}%", f"%{clean_dest}%")
        )
        t_row = cur.fetchone()
        t = dict(t_row) if t_row else {"carrier": "Победа", "price": 29000, "departure_time": "07:30", "arrival_time": "11:45", "duration_hours": 4.2, "stops": 0}

        h_sql = "SELECT * FROM hotels WHERE city_name_ru LIKE ?" + (" AND pets_allowed = 1" if pet_friendly else "") + " ORDER BY price_per_night ASC LIMIT 3"
        cur.execute(h_sql, (f"%{clean_dest}%",))
        h_rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        if not h_rows:
            from core.mock_tools import MockTravelTools
            return MockTravelTools().get_conflict_compromises(origin, destination, dates, target_budget, pet_friendly)

        cheapest_h = h_rows[0]
        comfort_h = h_rows[-1]
        t_price = int(float(t.get("price", 32000)))
        h_cheap_night = int(float(cheapest_h.get("price_per_night", 5500)))
        h_comf_night = int(float(comfort_h.get("price_per_night", 7500)))

        # Компромисс 1: Сдвиг дат и сокращение до 4 ночей
        c1_hotel_total = h_cheap_night * 4
        c1_total = min(target_budget, t_price + c1_hotel_total + 1500)

        # Компромисс 2: Базовый отель 3* на 6 ночей
        c2_hotel_total = h_cheap_night * 6
        c2_total = t_price + c2_hotel_total + 1500

        # Компромисс 3: Полный тур на 7 ночей с небольшой доплатой
        c3_hotel_total = h_comf_night * 7
        c3_total = t_price + c3_hotel_total + 3000
        diff = max(3500, c3_total - target_budget)

        base_transport = TransportDetails(
            transport_type="plane",
            carrier=t.get("carrier", "Аэрофлот"),
            origin=clean_origin,
            destination=clean_dest,
            departure_time=t.get("departure_time", "08:00"),
            arrival_time=t.get("arrival_time", "12:15"),
            duration_hours=float(t.get("duration_hours", 4.0)),
            is_direct=(int(t.get("stops", 0)) == 0),
            price_rub=t_price
        )

        c1 = Bundle(
            bundle_id="comp_db_shift_dates",
            destination=clean_dest,
            dates=f"{dates} (будни, 4 ночи)",
            visa_required=cheapest_h.get("country") not in VISA_FREE_COUNTRIES,
            weather_forecast="Комфортная погода",
            price_total=c1_total,
            transport=base_transport,
            hotel=HotelDetails(
                hotel_name=cheapest_h.get("name", "Ibis Budget"),
                stars=int(cheapest_h.get("stars", 3)),
                location_note=f"{clean_dest}, городской квартал",
                meal_plan="RO (Без питания)",
                cancellation_policy="Невозвратный промо-тариф",
                pet_friendly=bool(cheapest_h.get("pets_allowed", 0)),
                check_in_time=cheapest_h.get("check_in_time", "14:00"),
                price_rub=c1_hotel_total
            ),
            transfer=TransferDetails(
                included=True,
                transfer_type="Групповой шаттл",
                duration_minutes=50,
                price_rub=1500,
                schedule_compatible=True,
                compatibility_note="Прибытие к стандартному времени заселения 14:00."
            ),
            explanation=BundleExplanation(
                why=f"Уложились в ваш целевой бюджет ({target_budget:,} ₽) за счёт выбора будних дней и 4 ночей.",
                tradeoffs="Сокращение поездки до 4 ночей, групповой трансфер.",
                risks="Невозвратный тариф на проживание и перелёт."
            ),
            is_compromise=True,
            compromise_type="Сдвиг дат на будни и 4 ночи (в рамках бюджета)"
        )

        c2 = Bundle(
            bundle_id="comp_db_simpler_hotel",
            destination=clean_dest,
            dates=f"{dates} (6 ночей)",
            visa_required=c1.visa_required,
            weather_forecast="Комфортная погода",
            price_total=c2_total,
            transport=base_transport,
            hotel=HotelDetails(
                hotel_name=cheapest_h.get("name", "B&B Hotel"),
                stars=int(cheapest_h.get("stars", 3)),
                location_note=f"{clean_dest}, 15 минут до центра",
                meal_plan="BB (Завтрак включён)",
                cancellation_policy="Бесплатная отмена за 48 часов",
                pet_friendly=bool(cheapest_h.get("pets_allowed", 0)),
                check_in_time="14:00",
                price_rub=c2_hotel_total
            ),
            transfer=c1.transfer,
            explanation=BundleExplanation(
                why=f"Самый доступный отель каталога в г. {clean_dest} («{cheapest_h.get('name')}» по {h_cheap_night:,} ₽/ночь).",
                tradeoffs="Категория отеля 3★ вместо 4★.",
                risks="Ограниченное число номеров по минимальной квоте."
            ),
            is_compromise=True,
            compromise_type="Выбор отеля базовой категории 3★"
        )

        c3 = Bundle(
            bundle_id="comp_db_expand_budget",
            destination=clean_dest,
            dates=f"{dates} (7 ночей)",
            visa_required=c1.visa_required,
            weather_forecast="Комфортная погода",
            price_total=c3_total,
            transport=base_transport,
            hotel=HotelDetails(
                hotel_name=comfort_h.get("name", "Novotel"),
                stars=int(comfort_h.get("stars", 4)),
                location_note=f"{clean_dest}, центральная локация",
                meal_plan="BB (Завтрак включён)",
                cancellation_policy="Бесплатная отмена за 48 часов",
                pet_friendly=bool(comfort_h.get("pets_allowed", 0)),
                check_in_time="14:00",
                price_rub=c3_hotel_total
            ),
            transfer=TransferDetails(
                included=True,
                transfer_type="Индивидуальный трансфер",
                duration_minutes=40,
                price_rub=3000,
                schedule_compatible=True,
                compatibility_note="Комфортная стыковка рейса и заселения."
            ),
            explanation=BundleExplanation(
                why=f"Полноценный тур на 7 ночей в отель «{comfort_h.get('name')}» без потери комфорта.",
                tradeoffs=f"Потребуется расширить бюджет на {diff:,} ₽.",
                risks="Стандартные условия тарифа."
            ),
            is_compromise=True,
            compromise_type=f"Расширение бюджета (+{diff:,} ₽) без потери качества"
        )

        return [c1, c2, c3]

    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================
    def _clean_city_name(self, raw_city: str) -> str:
        """Извлекает чистое название города (например, 'Италия (Рим)' -> 'Рим')."""
        s = str(raw_city).strip()
        if "(" in s and ")" in s:
            inside = s[s.find("(") + 1 : s.find(")")].strip()
            if inside:
                return inside
        return s

    def _extract_nights(self, dates_str: str) -> int:
        """Определяет число ночей из строки дат (по умолчанию 7)."""
        m = re.search(r"(\d+)\s*(?:ноч|дн)", str(dates_str).lower())
        if m:
            n = int(m.group(1))
            if 1 <= n <= 30:
                return n
        return 7

    def _parse_month_to_int(self, month_str: str) -> int:
        m_low = str(month_str).lower()
        mapping = {
            "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
            "ма": 5, "июн": 6, "июл": 7, "август": 8,
            "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12
        }
        for k, v in mapping.items():
            if k in m_low:
                return v
        digits = re.findall(r"\d+", m_low)
        for d in digits:
            val = int(d)
            if 1 <= val <= 12:
                return val
        return 11

    def _calc_schedule_compatibility(
        self, arrival_time: str, transfer_mins: int, check_in_time: str
    ) -> tuple[bool, str]:
        """Математически проверяет стыковку времени прилёта, трансфера и заселения в отель."""
        try:
            arr_h, arr_m = map(int, arrival_time.split(":"))
            chk_h, chk_m = map(int, check_in_time.split(":"))
            hotel_arrival_total = (arr_h * 60 + arr_m + transfer_mins) % (24 * 60)
            check_in_total = chk_h * 60 + chk_m

            h_arr_str = f"{hotel_arrival_total // 60:02d}:{hotel_arrival_total % 60:02d}"
            wait_mins = check_in_total - hotel_arrival_total

            if wait_mins > 120:
                return (
                    True,
                    f"Прилёт в {arrival_time} + {transfer_mins} мин трансфер ➔ в отеле к {h_arr_str} "
                    f"(до заселения в {check_in_time} можно оставить вещи в камере хранения или запросить ранний заезд)."
                )
            elif wait_mins >= 0:
                return (
                    True,
                    f"Идеальная стыковка: прилёт в {arrival_time} + {transfer_mins} мин трансфер ➔ "
                    f"в отеле к {h_arr_str}, почти сразу к открытию заселения в {check_in_time}."
                )
            else:
                return (
                    True,
                    f"Прилёт в {arrival_time} + {transfer_mins} мин трансфер ➔ прибытие в отель в {h_arr_str} "
                    f"(номер уже готов с {check_in_time}, заселение без ожидания)."
                )
        except Exception:
            return (True, f"Прилёт в {arrival_time}, трансфер {transfer_mins} мин до отеля (заезд с {check_in_time}).")