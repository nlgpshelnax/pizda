from typing import Protocol, Optional, List
from pydantic import BaseModel, Field


class DestinationSuggestion(BaseModel):
    """Карточка направления для этапа 'Вдохновение' (когда задан только вайб)."""
    destination: str = Field(description="Страна и курорт/город")
    visa_required: bool = Field(description="Нужна ли виза гражданам РФ")
    visa_info: str = Field(description="Пояснение по визовому режиму")
    weather_summary: str = Field(description="Погода и температура воды/воздуха (Open-Meteo)")
    flight_duration_hours: float = Field(description="Ориентировочное время в пути (часов)")
    estimated_min_budget: int = Field(description="Ориентировочный бюджет на поездку (руб.)")
    why_suits: str = Field(description="Почему это направление подходит под вайб и сезон")


class TransportDetails(BaseModel):
    """Детали перелета / ЖД / автомаршрута (Travelpayouts / rzd-api / OSRM)."""
    transport_type: str = Field(default="plane", description="plane | train | car")
    carrier: str = Field(description="Авиакомпания, поезд РЖД или автомаршрут")
    origin: str
    destination: str
    departure_time: str = Field(description="Время отправления (например, '08:30')")
    arrival_time: str = Field(description="Время прибытия (например, '13:15')")
    duration_hours: float = Field(description="Время в пути в часах")
    is_direct: bool = Field(default=True, description="Прямой рейс или с пересадкой")
    price_rub: int = Field(description="Стоимость билетов туда-обратно (руб.)")


class HotelDetails(BaseModel):
    """Детали отеля (Travelpayouts / Viajante)."""
    hotel_name: str
    stars: int = Field(description="Категория отеля: 3, 4 или 5 звезд")
    location_note: str = Field(description="Расположение (1-я линия, расстояние до моря/центра)")
    meal_plan: str = Field(description="Питание (BB - завтраки, AI - все включено и т.д.)")
    cancellation_policy: str = Field(description="Условия отмены бронирования")
    pet_friendly: bool = Field(default=False, description="Разрешено ли проживание с животными")
    check_in_time: str = Field(default="14:00", description="Стандартное время заселения")
    price_rub: int = Field(description="Стоимость проживания за весь период (руб.)")


class TransferDetails(BaseModel):
    """Детали трансфера и проверка состыковки расписаний."""
    included: bool = Field(default=True)
    transfer_type: str = Field(description="Индивидуальный / групповой шаттл / аэроэкспресс")
    duration_minutes: int = Field(description="Время в пути от аэропорта/вокзала до отеля")
    price_rub: int = Field(default=0, description="Цена трансфера (0, если включен)")
    schedule_compatible: bool = Field(
        default=True,
        description="Стыкуется ли время прилета + трансфер со временем заселения в отель"
    )
    compatibility_note: str = Field(
        description="Пояснение по стыковке (например: 'Прилет в 12:30 + 45 мин трансфер = в отеле к 13:15, заселение в 14:00 без долгого ожидания')"
    )


class BundleExplanation(BaseModel):
    """Обязательный блок Explainability по требованиям хакатона."""
    why: str = Field(description="Почему этот вариант подходит под запрос пользователя")
    tradeoffs: str = Field(description="На какие компромиссы пришлось пойти")
    risks: str = Field(description="Возможные риски, о которых важно предупредить")


class Bundle(BaseModel):
    """Готовый собранный тур (бандл) для выдачи пользователю."""
    bundle_id: str
    destination: str
    dates: str
    visa_required: bool
    weather_forecast: str
    price_total: int = Field(description="Итоговая цена: транспорт + отель + трансфер")
    transport: TransportDetails
    hotel: HotelDetails
    transfer: TransferDetails
    explanation: BundleExplanation

    # Поля для ветки разрешения конфликтов (Constraint Relaxation)
    is_compromise: bool = Field(default=False, description="Является ли вариант компромиссным")
    compromise_type: Optional[str] = Field(
        default=None,
        description="Тип компромисса: 'shift_dates' | 'simpler_hotel' | 'over_budget'"
    )


class TravelTools(Protocol):
    """
    КОНТРАКТ ДЛЯ БЭКЕНД-ИНЖЕНЕРА:
    Все функции, которые вызывает ядро агента (workflow.py).
    """

    def search_destinations(
        self,
        vibe: str,
        month: str,
        visa_preference: Optional[str] = None
    ) -> List[DestinationSuggestion]:
        """Подбор направлений по вайбу и сезону (несколько с визой, несколько без)."""
        ...

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
        """Сборка топ-вариантов готовых туров (билеты + трансфер + отель)."""
        ...

    def get_conflict_compromises(
        self,
        origin: str,
        destination: str,
        dates: str,
        target_budget: int,
        pet_friendly: bool = False
    ) -> List[Bundle]:
        """
        Алгоритм Constraint Relaxation:
        Если бюджет слишком мал, возвращает 3 альтернативы (сдвиг дат, проще отель, выше бюджет).
        """
        ...

    def replace_hotel_only(
        self,
        current_bundle: Bundle,
        pet_friendly: bool = False,
        stars: Optional[int] = None
    ) -> Bundle:
        """
        Хирургическая пересборка (Surgical Invalidation):
        Меняет только отель в собранном туре, сохраняя авиабилеты и даты.
        """
        ...