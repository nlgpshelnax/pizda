import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from trip_data.models import TripRequest
from trip_data.plan_models import DemoOrder, Plan, ServiceRequest
from trip_data.validation import total_price, validate_bundle


class StateError(Exception):
    def __init__(self, code: str, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, version INTEGER, payload TEXT);
            CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, plan_id TEXT,
              idem TEXT, version INTEGER, payload TEXT, UNIQUE(plan_id,idem));
            CREATE TABLE IF NOT EXISTS services(id TEXT PRIMARY KEY, order_id TEXT,
              idem TEXT, kind TEXT, payload TEXT, UNIQUE(order_id,idem));
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def create(self, plan: Plan):
        with self.connect() as db:
            db.execute(
                "INSERT INTO plans VALUES(?,?,?)", (plan.id, plan.version, plan.model_dump_json())
            )
        return plan

    def get(self, plan_id: str) -> Plan:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            raise StateError("PLAN_NOT_FOUND", 404)
        return Plan.model_validate_json(row[0])

    def save(self, plan: Plan, expected: int):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE plans SET version=?,payload=? WHERE id=? AND version=?",
                (plan.version, plan.model_dump_json(), plan.id, expected),
            ).rowcount
            if not changed:
                raise StateError("STALE_PLAN_VERSION")
        return plan

    def checkout(self, plan_id: str, version: int, key: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT payload,version FROM orders WHERE plan_id=? AND idem=?", (plan_id, key)
            ).fetchone()
            if old:
                if old[1] != version:
                    raise StateError("IDEMPOTENCY_CONFLICT")
                return DemoOrder.model_validate_json(old[0])
            row = db.execute("SELECT payload FROM plans WHERE id=?", (plan_id,)).fetchone()
            if not row:
                raise StateError("PLAN_NOT_FOUND", 404)
            plan = Plan.model_validate_json(row[0])
            if version != plan.version:
                raise StateError("STALE_PLAN_VERSION")
            candidate = next(
                (o.bundle for o in plan.search.options if o.bundle.id == plan.selected_id), None
            )
            if candidate is None:
                raise StateError("SELECTION_REQUIRED")
            if any(i.severity == "error" for i in validate_bundle(candidate, plan.request)):
                raise StateError("QUOTE_NO_LONGER_VALID")
            order = DemoOrder(
                id=str(uuid4()),
                plan_id=plan_id,
                plan_version=version,
                bundle=candidate.model_copy(deep=True),
                total=total_price(candidate),
                created_at=datetime.now(UTC),
            )
            db.execute(
                "INSERT INTO orders VALUES(?,?,?,?,?)",
                (order.id, plan_id, key, version, order.model_dump_json()),
            )
            return order

    def order(self, order_id: str):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise StateError("ORDER_NOT_FOUND", 404)
        return DemoOrder.model_validate_json(row[0])

    def request_service(self, order_id: str, kind: str, key: str):
        self.order(order_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload,kind FROM services WHERE order_id=? AND idem=?", (order_id, key)
            ).fetchone()
            if row:
                if row[1] != kind:
                    raise StateError("IDEMPOTENCY_CONFLICT")
                return ServiceRequest.model_validate_json(row[0])
            service = ServiceRequest(id=str(uuid4()), order_id=order_id, kind=kind)
            db.execute(
                "INSERT INTO services VALUES(?,?,?,?,?)",
                (service.id, order_id, key, kind, service.model_dump_json()),
            )
            return service

    def services(self, order_id: str):
        self.order(order_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM services WHERE order_id=? ORDER BY rowid", (order_id,)
            ).fetchall()
        return [ServiceRequest.model_validate_json(row[0]) for row in rows]

    def decide_service(self, order_id: str, service_id: str, status: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM services WHERE id=? AND order_id=?", (service_id, order_id)
            ).fetchone()
            if not row:
                raise StateError("SERVICE_NOT_FOUND", 404)
            service = ServiceRequest.model_validate_json(row[0])
            if service.status != "pending" and service.status != status:
                raise StateError("SERVICE_ALREADY_RESOLVED")
            service.status = status
            service.note = "Simulated supplier decision; no real booking, charge or confirmation"
            db.execute(
                "UPDATE services SET payload=? WHERE id=?", (service.model_dump_json(), service.id)
            )
            return service


def apply_patch(request: TripRequest, changes: dict) -> TripRequest:
    original = request.model_dump(mode="json")
    if set(changes) - set(original):
        raise ValueError("Unknown patch fields")
    for field, value in changes.items():
        if isinstance(value, dict) and isinstance(original.get(field), dict):
            if set(value) - set(original[field]):
                raise ValueError("Unknown nested patch fields")
            original[field] = {**original[field], **value}
        else:
            original[field] = value
    return TripRequest.model_validate(json.loads(json.dumps(original)))
