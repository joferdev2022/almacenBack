"""Dinero, fechas y serialización de Caja; no modifica modelos históricos."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException

LIMA = ZoneInfo("America/Lima")
ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value):
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise InvalidOperation
        return amount.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError) as error:
        raise HTTPException(422, "El monto no es válido.") from error


def object_id(value, label="jornada"):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, f"El identificador de {label} no es válido.")
    return ObjectId(value)


def serialize(value):
    if isinstance(value, dict):
        return {"id" if key == "_id" else key: serialize(item)
                for key, item in value.items() if key not in ("huellaApertura", "huellaCierre", "huella")}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(LIMA).isoformat()
    return value


def fingerprint(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def date_filter(start: date | None, end: date | None):
    if start and end and start > end:
        raise HTTPException(422, "La fecha desde no puede ser posterior a la fecha hasta.")
    query = {}
    if start:
        query["$gte"] = datetime.combine(start, time.min, tzinfo=LIMA).astimezone(timezone.utc)
    if end:
        try:
            query["$lt"] = datetime.combine(end + timedelta(days=1), time.min, tzinfo=LIMA).astimezone(timezone.utc)
        except OverflowError as error:
            raise HTTPException(422, "La fecha hasta está fuera del rango admitido.") from error
    return query
