"""Build synthetic component fixtures from the explicit mock bundle source."""

import json
from pathlib import Path

from trip_data.components import (
    ComponentCatalog,
    HotelProperty,
    HotelQuote,
    TransferQuote,
    TransportQuote,
)
from trip_data.models import Bundle


def convert(bundles):
    properties, hotels, transport, transfers = {}, [], [], []
    for bundle in bundles:
        if bundle.provenance.kind != "mock":
            raise ValueError("This fixture tool only accepts synthetic data")
        hotel = bundle.hotel
        property_id = hotel.location_id or f"property-{hotel.city}"
        properties[property_id] = HotelProperty(
            id=property_id,
            name=hotel.name,
            city=hotel.city,
            timezone=hotel.timezone or "Europe/Moscow",
            stars=hotel.stars,
            rating=hotel.rating,
            review_count=hotel.review_count,
        )
        hotels.append(
            HotelQuote(
                id=bundle.id + "-hotel",
                property_id=property_id,
                scope=bundle.request,
                check_in_at=hotel.check_in_at,
                check_out_at=hotel.check_out_at,
                latest_check_in_at=hotel.latest_check_in_at,
                breakfast=hotel.breakfast,
                pets_allowed=hotel.pets_allowed,
                max_guests=hotel.max_guests,
                children_allowed=hotel.children_allowed,
                price=hotel.price,
                mandatory_fees_known=bundle.mandatory_fees_known,
                provenance=bundle.provenance,
            )
        )
        for direction, leg, transfer in zip(
            ("outbound", "inbound"),
            (bundle.outbound, bundle.inbound),
            bundle.transfers(),
            strict=True,
        ):
            transport.append(
                TransportQuote(
                    id=bundle.id + "-" + direction,
                    scope=bundle.request,
                    direction=direction,
                    transport=leg,
                    provenance=bundle.provenance,
                )
            )
            transfers.append(
                TransferQuote(
                    id=bundle.id + "-transfer-" + direction,
                    scope=bundle.request,
                    direction=direction,
                    hotel_property_id=property_id,
                    transfer=transfer,
                    provenance=bundle.provenance,
                )
            )
    return ComponentCatalog(
        properties=list(properties.values()),
        hotels=hotels,
        transport=transport,
        transfers=transfers,
    )


if __name__ == "__main__":
    bundles = [
        Bundle.model_validate(v)
        for v in json.loads(Path("data/fixtures/component-source.json").read_text())
    ]
    Path("data/fixtures/components.json").write_text(
        convert(bundles).model_dump_json(indent=2) + "\n"
    )
