from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trip_data.models import Bundle, Issue, Money, TripRequest


def total_price(bundle: Bundle) -> Money:
    outward, inward = bundle.transfers()
    amount = sum(
        (
            bundle.hotel.price.amount,
            bundle.outbound.price.amount,
            bundle.inbound.price.amount,
            outward.price.amount,
            inward.price.amount,
        ),
        Decimal("0"),
    )
    return Money(amount=amount)


def validate_bundle(
    bundle: Bundle, request: TripRequest, now: datetime | None = None
) -> list[Issue]:
    issues: list[Issue] = []

    def add(code: str, message: str, severity: str = "error") -> None:
        issues.append(Issue(code=code, message=message, severity=severity))

    exact = ("origin", "destination", "check_in", "check_out", "guests")
    if any(getattr(bundle.request, key) != getattr(request, key) for key in exact):
        add("QUOTE_SCOPE_MISMATCH", "Цена не применима к этим датам, маршруту или гостям")
    if (
        bundle.hotel.city != request.destination
        or bundle.outbound.origin != request.origin
        or bundle.outbound.destination != request.destination
        or bundle.inbound.origin != request.destination
        or bundle.inbound.destination != request.origin
    ):
        add("ROUTE_MISMATCH", "Компоненты относятся к разным маршрутам")
    if (
        bundle.hotel.check_in_at.date() != request.check_in
        or bundle.hotel.check_out_at.date() != request.check_out
    ):
        add("STAY_MISMATCH", "Даты проживания не совпадают с запросом")
    if bundle.hotel.check_out_at <= bundle.hotel.check_in_at:
        add("INVALID_STAY", "Выезд должен быть после заселения")
    if bundle.hotel.latest_check_in_at < bundle.hotel.check_in_at:
        add("INVALID_CHECKIN_WINDOW", "Некорректное окно заселения")
    for leg in (bundle.outbound, bundle.inbound):
        issues.extend(validate_segments(leg))
        if leg.arrival_at <= leg.departure_at:
            add("INVALID_TRANSPORT_TIME", "Прибытие должно быть после отправления")
    if bundle.inbound.departure_at <= bundle.outbound.arrival_at:
        add("INVALID_RETURN_TIME", "Обратная дорога раньше прибытия")
    guests = request.guests
    outward, inward = bundle.transfers()
    guest_count = guests.adults + len(guests.children_ages)
    if bundle.hotel.max_guests is None:
        add("HOTEL_CAPACITY_UNCONFIRMED", "Вместимость номера не подтверждена")
    elif guest_count > bundle.hotel.max_guests:
        add("HOTEL_CAPACITY", "Не хватает мест в номере")
    if guests.children_ages and bundle.hotel.children_allowed is not True:
        add("CHILDREN_UNCONFIRMED", "Правила размещения детей не подтверждены")
    if any(guest_count > transfer.capacity for transfer in (outward, inward)):
        add("TRANSFER_CAPACITY", "Не хватает мест в трансфере")
    if guests.pets and (
        bundle.hotel.pets_allowed is not True
        or any(transfer.pets_allowed is not True for transfer in (outward, inward))
    ):
        add("PETS_UNCONFIRMED", "Размещение или трансфер с животным не подтверждены")
    for transfer in (outward, inward):
        if request.child_seats_required and (
            transfer.child_seats is None or transfer.child_seats < request.child_seats_required
        ):
            add("CHILD_SEAT_UNCONFIRMED", "Нет подтверждённого детского кресла")
    hotel_location = bundle.hotel.location_id or bundle.hotel.id
    for transfer, origin, destination in (
        (outward, bundle.outbound.arrival_location, hotel_location),
        (inward, hotel_location, bundle.inbound.departure_location),
    ):
        if (transfer.origin and origin and transfer.origin != origin) or (
            transfer.destination and destination and transfer.destination != destination
        ):
            add("TRANSFER_ROUTE_MISMATCH", "Трансфер не совпадает с терминалом/отелем")
    if request.breakfast_required and not bundle.hotel.breakfast:
        add("BREAKFAST_REQUIRED", "Завтрак не включён")
    if bundle.hotel.stars < request.min_stars:
        add("STARS_REQUIRED", "Категория отеля ниже обязательной")
    if request.budget and total_price(bundle).amount > request.budget.amount:
        add("OVER_BUDGET", "Полная стоимость превышает бюджет")
    if not bundle.mandatory_fees_known:
        add("UNKNOWN_FEES", "Неизвестны обязательные доплаты")
    if bundle.provenance.kind == "mock":
        add("DEMO_DATA", "Синтетические данные: цена и наличие не подтверждены", "warning")
    elif bundle.provenance.valid_until <= (now or datetime.now(UTC)):
        add("QUOTE_EXPIRED", "Срок действия предложения истёк")
    for component in (bundle.hotel, bundle.outbound, bundle.inbound, outward, inward):
        provenance = component.provenance
        if provenance is None:
            if bundle.provenance.kind != "mock":
                add("SOURCE_UNCONFIRMED", "Не указан источник отдельного компонента")
        elif provenance.kind == "mock":
            if bundle.provenance.kind != "mock":
                add("MIXED_MOCK_DATA", "Синтетический компонент недопустим в реальной поездке")
        elif provenance.valid_until <= (now or datetime.now(UTC)):
            add("COMPONENT_QUOTE_EXPIRED", "Истёк срок действия компонента поездки")
    default_arrival = (
        15 if bundle.outbound.mode == "train" else (90 if bundle.outbound.international else 60)
    )
    arrival_buffer = max(default_arrival, bundle.outbound.arrival_buffer_minutes or 0)
    hotel_arrival = bundle.outbound.arrival_at + timedelta(
        minutes=arrival_buffer + outward.duration_minutes
    )
    if hotel_arrival < bundle.hotel.check_in_at and not bundle.hotel.early_check_in_confirmed:
        add(
            "EARLY_CHECKIN_UNCONFIRMED",
            "Придётся ждать заселения; ранний заезд не подтверждён",
            "warning",
        )
    if hotel_arrival > bundle.hotel.latest_check_in_at:
        add("MISSED_CHECKIN", "После трансфера заселиться уже нельзя")
    ready_at = (
        hotel_arrival
        if bundle.hotel.early_check_in_confirmed
        else max(hotel_arrival, bundle.hotel.check_in_at)
    )
    if ready_at >= bundle.hotel.check_out_at:
        add("NO_STAY_WINDOW", "После прибытия не остаётся времени проживания")
    inbound = bundle.inbound
    default_departure = 45 if inbound.mode == "train" else (180 if inbound.international else 120)
    departure_buffer = max(default_departure, inbound.departure_buffer_minutes or 0)
    leave_hotel = inbound.departure_at - timedelta(
        minutes=departure_buffer + inward.duration_minutes
    )
    for transfer, pickup in (
        (outward, bundle.outbound.arrival_at + timedelta(minutes=arrival_buffer)),
        (inward, leave_hotel),
    ):
        if (transfer.available_from and pickup < transfer.available_from) or (
            transfer.available_until and pickup > transfer.available_until
        ):
            add("TRANSFER_CLOSED", "Трансфер недоступен во время посадки")
    if leave_hotel > bundle.hotel.check_out_at:
        add("WAIT_AFTER_CHECKOUT", "После выезда нужно ждать обратного трансфера", "warning")
    if leave_hotel <= ready_at:
        add("RETURN_UNREACHABLE", "Не хватает времени на проживание и обратный трансфер")
    if inbound.international or bundle.outbound.international:
        add("VISA_UNVERIFIED", "Правила въезда требуют отдельной проверки", "warning")
    return issues


def validate_segments(leg) -> list[Issue]:
    issues = []

    def fail(code, message):
        issues.append(Issue(code=code, severity="error", message=message))

    if not leg.segments:
        return issues
    segments = leg.segments
    if segments[0].departure_at != leg.departure_at or segments[-1].arrival_at != leg.arrival_at:
        fail("SEGMENT_TIME_MISMATCH", "Сегменты не совпадают с полным маршрутом")
    if (leg.departure_location and segments[0].origin != leg.departure_location) or (
        leg.arrival_location and segments[-1].destination != leg.arrival_location
    ):
        fail("SEGMENT_ROUTE_MISMATCH", "Терминалы сегментов не совпадают с маршрутом")
    for segment in segments:
        if segment.arrival_at <= segment.departure_at:
            fail("INVALID_SEGMENT_TIME", "Неверный порядок времени сегмента")
    for before, after in zip(segments, segments[1:], strict=False):
        minimum = 90 if leg.international else (45 if leg.mode == "train" else 60)
        if before.destination != after.origin:
            connection = next(
                (
                    c
                    for c in leg.connections
                    if c.origin == before.destination
                    and c.destination == after.origin
                    and c.confirmed
                ),
                None,
            )
            if connection is None:
                fail("AIRPORT_CHANGE_UNCONFIRMED", "Переезд между терминалами не подтверждён")
                continue
            minimum += connection.duration_minutes
        if after.departure_at - before.arrival_at < timedelta(minutes=minimum):
            fail("CONNECTION_TOO_SHORT", "Недостаточно времени на пересадку")
    return issues
