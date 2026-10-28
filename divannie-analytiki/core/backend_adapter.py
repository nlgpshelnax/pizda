import os
import re
import json
import uuid
import urllib.request
import urllib.error
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
from core.mock_tools import MockTravelTools


class BackendTravelTools(TravelTools):
    """
    HTTP-адаптер к REST API сервиса trip_data (бэкенд на порту 8000).
    Точно соответствует контрактам из core/tools_interface.py.
    При сбое или таймауте автоматически переключается на MockTravelTools.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("BACKEND_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.fallback = MockTravelTools()
        self.last_plan_id: Optional[str] = None
        self.last_plan_version: int = 1
        self.last_order_id: Optional[str] = None

    # =========================================================================
    # ВНУТРЕННИЕ СЕТЕВЫЕ МЕТОДЫ (СТАНДАРТНЫЙ URLLIB)
    # =========================================================================
    def _send_request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 4.0
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}

        try:
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status in (200, 201):
                    return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"[BackendTravelTools] HTTP {e.code} на {path}")
            return None
        except Exception as e:
            print(f"[BackendTravelTools Warning] Ошибка обращения к {url}: {e}")
            return None
        return None

    # =========================================================================
    # 1. ПОИСК НАПРАВЛЕНИЙ (POST /api/v1/explore)
    # =========================================================================
    def search_destinations(
        self,
        vibe: str,
        month: str,
        visa_preference: Optional[str] = None
    ) -> List[DestinationSuggestion]:
        month_int = self._normalize_month_to_int(month)
        vibe_key = self._extract_clean_vibe(vibe)

        payload = {"month": month_int, "vibe": vibe_key}
        resp = self._send_request("POST", "/api/v1/explore", payload)

        if resp and isinstance(resp, list):
            suggestions: List[DestinationSuggestion] = []
            for item in resp:
                suggestions.append(
                    DestinationSuggestion(
                        destination=item.get("destination", item.get("city", "Курорт")),
                        visa_required=bool(item.get("visa_required", False)),
                        visa_info=item.get("visa_info", "Безвизовый въезд для граждан РФ"),
                        weather_summary=item.get("weather_summary", "Комфортная погода для отдыха"),
                        flight_duration_hours=float(item.get("flight_duration_hours", 4.0)),
                        estimated_min_budget=int(float(item.get("estimated_min_budget", 75000))),
                        why_suits=item.get("why_suits", f"Отличное направление под формат отдыха '{vibe}'")
                    )
                )
            if suggestions:
                return suggestions

        return self.fallback.search_destinations(vibe, month, visa_preference)

    # =========================================================================
    # 2. ПОИСК И СБОРКА ТУРОВ (POST /api/v1/plans)
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
        check_in, check_out = self._parse_dates_range(dates)
        adults_count = self._parse_adults_count(guests)

        trip_request_payload = {
            "origin": origin,
            "destination": destination,
            "dates": dates,
            "check_in": check_in,
            "check_out": check_out,
            "budget": budget,
            "guests": {
                "adults": adults_count,
                "children_ages": [],
                "pets": 1 if pet_friendly else 0
            },
            "hotel_stars": stars or 4,
            "transport_type": transport_type or "flight"
        }

        # 1. Основной запрос создания плана
        resp = self._send_request("POST", "/api/v1/plans", trip_request_payload)

        # 2. Резервный запрос через поиск
        if not resp:
            resp = self._send_request(
                "POST",
                "/api/v1/bundles/search",
                {"request": trip_request_payload, "plan_version": self.last_plan_version}
            )

        if resp:
            self.last_plan_id = resp.get("id", self.last_plan_id)
            self.last_plan_version = resp.get("version", 1)

            search_container = resp.get("search", resp)
            raw_bundles = search_container.get("bundles", search_container.get("options", []))

            bundles: List[Bundle] = []
            for b in raw_bundles:
                try:
                    bundles.append(self._map_backend_bundle_to_core(b, destination, dates))
                except Exception as ex:
                    print(f"[BackendTravelTools] Ошибка маппинга бандла: {ex}")
                    continue

            if bundles:
                return bundles

        return self.fallback.get_trip_bundles(
            origin=origin,
            destination=destination,
            dates=dates,
            budget=budget,
            guests=guests,
            pet_friendly=pet_friendly,
            stars=stars,
            transport_type=transport_type
        )

    # =========================================================================
    # 3. ТОЧЕЧНАЯ ПЕРЕСБОРКА (PATCH /api/v1/plans/{id})
    # =========================================================================
    def replace_hotel_only(
        self,
        current_bundle: Bundle,
        pet_friendly: bool = False,
        stars: Optional[int] = None
    ) -> Bundle:
        if self.last_plan_id:
            patch_payload = {
                "base_version": self.last_plan_version,
                "changes": {
                    "guests": {"pets": 1 if pet_friendly else 0},
                    "hotel_stars": stars or current_bundle.hotel.stars
                }
            }
            resp = self._send_request("PATCH", f"/api/v1/plans/{self.last_plan_id}", patch_payload)

            if resp:
                self.last_plan_version = resp.get("version", self.last_plan_version + 1)
                search_container = resp.get("search", {})
                raw_bundles = search_container.get("bundles", search_container.get("options", []))

                if raw_bundles:
                    return self._map_backend_bundle_to_core(
                        raw_bundles[0],
                        current_bundle.destination,
                        current_bundle.dates
                    )

        return self.fallback.replace_hotel_only(current_bundle, pet_friendly, stars)

    # =========================================================================
    # 4. РАЗРЕШЕНИЕ КОНФЛИКТОВ (CONSTRAINT RELAXATION)
    # =========================================================================
    def get_conflict_compromises(
        self,
        origin: str,
        destination: str,
        dates: str,
        target_budget: int,
        pet_friendly: bool = False
    ) -> List[Bundle]:
        return self.fallback.get_conflict_compromises(
            origin=origin,
            destination=destination,
            dates=dates,
            target_budget=target_budget,
            pet_friendly=pet_friendly
        )

    # =========================================================================
    # 5. СЕРВИСНЫЙ ЗАПРОС (POST /api/v1/orders/{id}/services)
    # =========================================================================
    def request_service(self, kind: str) -> Optional[Dict[str, Any]]:
        order_id = self.last_order_id or self.last_plan_id
        if not order_id:
            return None

        payload = {"kind": kind, "idempotency_key": str(uuid.uuid4())}
        return self._send_request("POST", f"/api/v1/orders/{order_id}/services", payload)

    # =========================================================================
    # МАППЕР В СТРОГИЕ PYDANTIC-МОДЕЛИ ИЗ tools_interface.py
    # =========================================================================
    def _map_backend_bundle_to_core(
        self,
        raw: Dict[str, Any],
        default_destination: str,
        dates: str
    ) -> Bundle:
        hotel_raw = raw.get("hotel", {})
        transport_raw = raw.get("transport", raw.get("flight", {}))
        transfer_raw = raw.get("transfer", {})
        expl_raw = raw.get("explanation", {})

        total_price = int(float(raw.get("price_total", raw.get("total_price", 73000))))
        hotel_price = int(float(hotel_raw.get("total_price", hotel_raw.get("price_rub", 42000))))
        transport_price = int(float(transport_raw.get("price_rub", transport_raw.get("price", 28000))))
        transfer_price = int(float(transfer_raw.get("price_rub", transfer_raw.get("price", 3000))))

        return Bundle(
            bundle_id=str(raw.get("bundle_id", raw.get("id", "bundle_from_db"))),
            destination=raw.get("destination", default_destination),
            dates=dates,
            visa_required=bool(raw.get("visa_required", False)),
            weather_forecast=raw.get("weather_forecast", "Ясно, без осадков, воздух +20..+24°C"),
            price_total=total_price,
            transport=TransportDetails(
                transport_type=transport_raw.get("transport_type", transport_raw.get("type", "plane")),
                carrier=transport_raw.get("carrier", "Аэрофлот"),
                origin=transport_raw.get("origin", "Москва"),
                destination=transport_raw.get("destination", default_destination),
                departure_time=transport_raw.get("departure_time", "07:45"),
                arrival_time=transport_raw.get("arrival_time", "11:30"),
                duration_hours=float(transport_raw.get("duration_hours", 3.75)),
                is_direct=bool(transport_raw.get("is_direct", True)),
                price_rub=transport_price
            ),
            hotel=HotelDetails(
                hotel_name=hotel_raw.get("hotel_name", hotel_raw.get("name", "Отель у моря")),
                stars=int(hotel_raw.get("stars", 4)),
                location_note=hotel_raw.get("location_note", "1-я линия, 50 метров до моря"),
                meal_plan=hotel_raw.get("meal_plan", "BB (Завтрак включён)"),
                cancellation_policy=hotel_raw.get("cancellation_policy", "Бесплатная отмена за 48 часов"),
                pet_friendly=bool(hotel_raw.get("pet_friendly", hotel_raw.get("pets_allowed", False))),
                check_in_time=hotel_raw.get("check_in_time", "14:00"),
                price_rub=hotel_price
            ),
            transfer=TransferDetails(
                included=bool(transfer_raw.get("included", True)),
                transfer_type=transfer_raw.get("transfer_type", "Индивидуальный трансфер"),
                duration_minutes=int(transfer_raw.get("duration_minutes", 40)),
                price_rub=transfer_price,
                schedule_compatible=bool(transfer_raw.get("schedule_compatible", True)),
                compatibility_note=transfer_raw.get(
                    "compatibility_note",
                    "Прилёт в 11:30 + 40 мин трансфер = в отеле к 12:10 (до заселения в 14:00)."
                )
            ),
            explanation=BundleExplanation(
                why=expl_raw.get("why", "Прямой утренний рейс и отель 4★ оптимально подходят под запрос."),
                tradeoffs=expl_raw.get("tradeoffs", "Стандартные условия бронирования без доплат."),
                risks=expl_raw.get("risks", "Высокий спрос на выбранные даты (DEMO_DATA).")
            ),
            is_compromise=bool(raw.get("is_compromise", False)),
            compromise_type=raw.get("compromise_type", None)
        )

    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================
    def _normalize_month_to_int(self, month_str: str) -> int:
        m_lower = str(month_str).lower()
        mapping = {
            "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
            "ма": 5, "июн": 6, "июл": 7, "август": 8,
            "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12
        }
        for k, v in mapping.items():
            if k in m_lower:
                return v
        digits = re.findall(r"\d+", m_lower)
        if digits:
            num = int(digits[-1])
            if 1 <= num <= 12:
                return num
        return 11

    def _extract_clean_vibe(self, vibe_raw: str) -> str:
        v_low = str(vibe_raw).lower()
        if any(w in v_low for w in ["мор", "пляж", "купат", "beach"]):
            return "beach"
        if any(w in v_low for w in ["лыж", "гор", "сноуборд", "ski"]):
            return "ski"
        if any(w in v_low for w in ["музе", "экскурс", "архитектур", "culture"]):
            return "culture"
        if any(w in v_low for w in ["тишин", "релакс", "quiet"]):
            return "quiet"
        return "beach"

    def _parse_dates_range(self, dates_str: str) -> tuple[str, str]:
        if "_" in dates_str:
            parts = dates_str.split("_")
            return parts[0], parts[1]
        return "2026-11-12", "2026-11-17"

    def _parse_adults_count(self, guests_str: Optional[str]) -> int:
        if not guests_str:
            return 2
        digits = re.findall(r"\d+", str(guests_str))
        return int(digits[0]) if digits else 2