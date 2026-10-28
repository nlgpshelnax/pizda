"""Import a reviewed provider export. Never maps a price to different dates/occupancy."""

import argparse
import json
from urllib.parse import urlsplit

from trip_data.components import HotelQuote
from trip_data.config import Settings
from trip_data.database import CatalogDB, minor


def import_rates(database, payload, source="reviewed-hotel-rates"):
    def ingest(db, values, source):
        quotes = [HotelQuote.model_validate(q) for q in values]
        for quote in quotes:
            url = urlsplit(quote.provenance.source_url or "")
            if (
                quote.provenance.kind != "snapshot"
                or url.scheme != "https"
                or not url.hostname
                or url.username
            ):
                raise ValueError("Reviewed snapshots need a public HTTPS evidence URL")
            prop = db.execute(
                "SELECT * FROM hotels WHERE id=? AND active=1", (quote.property_id,)
            ).fetchone()
            if not prop or prop["source_mode"] == "mock":
                raise ValueError("Quote must reference an existing real property")
            if prop["city_id"] != database.city_id(db, quote.scope.destination):
                raise ValueError("Property and request destination differ")
            database.dates(db, quote.scope.check_in, quote.scope.check_out)
            database.upsert(
                db,
                "hotel_quotes",
                dict(
                    id=source + ":" + quote.id,
                    hotel_id=quote.property_id,
                    guest_id=database.guest(db, quote.scope),
                    check_in=quote.scope.check_in.isoformat(),
                    check_out=quote.scope.check_out.isoformat(),
                    currency=quote.price.currency,
                    amount_minor=minor(quote.price.amount),
                    price_basis=quote.price_basis,
                    breakfast=quote.breakfast,
                    pets_allowed=quote.pets_allowed,
                    max_guests=quote.max_guests,
                    mandatory_fees_known=quote.mandatory_fees_known,
                    source_mode="snapshot",
                    source_id=source,
                    fetched_at=quote.provenance.fetched_at.isoformat(),
                    valid_until=quote.provenance.valid_until.isoformat(),
                    payload_json=quote.model_dump_json(),
                ),
            )
        return len(quotes)

    result = database.ingest(source, payload, ingest)
    database.populate_auxiliary()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    args = parser.parse_args()
    database = CatalogDB(Settings().database_path)
    print(import_rates(database, json.loads(open(args.source).read())))
