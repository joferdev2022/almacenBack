import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from app.db.mongo import sales_liquorDb
from app.utils.helpers_liquor import sale_helper


LIMA = ZoneInfo("America/Lima")


def ensure_credit_liquor_indexes():
    sales_liquorDb.create_index(
        [("local", ASCENDING), ("condicionPago", ASCENDING), ("fechaVencimiento", ASCENDING)],
        name="credits_liquor_by_due_date",
    )
    sales_liquorDb.create_index(
        [("local", ASCENDING), ("clienteCredito.nombre", ASCENDING)],
        name="credits_liquor_by_customer",
    )


def _object_id(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="El ID del crédito no es válido.")
    return ObjectId(value)


def _money(value, label: str):
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{label} no es válido.") from exc
    if amount < 0:
        raise HTTPException(status_code=422, detail=f"{label} no puede ser negativo.")
    return amount


def _payment_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="La fecha del abono no es válida.") from exc
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=LIMA)
    return value.astimezone(timezone.utc)


def _base_query(local: int, search: str | None = None):
    clauses = [
        {"local": local},
        {
            "$or": [
                {"condicionPago": "credito"},
                {"estado": "credito", "condicionPago": {"$exists": False}},
            ]
        },
    ]
    if search and search.strip():
        clauses.append(
            {
                "$or": [
                    {
                        "clienteCredito.nombre": {
                            "$regex": re.escape(search.strip()),
                            "$options": "i",
                        }
                    },
                    {
                        "clienteCredito.telefono": {
                            "$regex": re.escape(search.strip()),
                            "$options": "i",
                        }
                    },
                ]
            }
        )
    return {"$and": clauses}


def _filtered_query(local: int, search: str | None, status: str | None):
    query = _base_query(local, search)
    clauses = query["$and"]
    if status == "pagado":
        clauses.append({"pago.saldoPendiente": {"$lte": 0}})
    elif status == "parcial":
        clauses.extend(
            [{"pago.pagado": {"$gt": 0}}, {"pago.saldoPendiente": {"$gt": 0}}]
        )
    elif status == "pendiente":
        clauses.extend(
            [{"pago.pagado": {"$lte": 0}}, {"pago.saldoPendiente": {"$gt": 0}}]
        )
    elif status == "vencido":
        clauses.extend(
            [
                {"pago.saldoPendiente": {"$gt": 0}},
                {"fechaVencimiento": {"$lt": datetime.now(timezone.utc)}},
            ]
        )
    return query


def _summary(local: int, search: str | None = None):
    result = {
        "totalCredito": 0.0,
        "totalPagado": 0.0,
        "saldoPendiente": 0.0,
        "creditosPendientes": 0,
        "creditosVencidos": 0,
    }
    now = datetime.now(timezone.utc)
    for sale in sales_liquorDb.find(_base_query(local, search)):
        payment = sale.get("pago", {})
        total = _money(payment.get("total", 0), "El total")
        paid = _money(payment.get("pagado", 0), "El monto pagado")
        balance = _money(
            payment.get("saldoPendiente", max(total - paid, 0)),
            "El saldo pendiente",
        )
        result["totalCredito"] += total
        result["totalPagado"] += paid
        result["saldoPendiente"] += balance
        if balance > 0:
            result["creditosPendientes"] += 1
            due = sale.get("fechaVencimiento")
            if isinstance(due, datetime):
                comparable = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                if comparable < now:
                    result["creditosVencidos"] += 1

    for field in ("totalCredito", "totalPagado", "saldoPendiente"):
        result[field] = round(result[field], 2)
    return result


async def retrieve_credit_summary_liquor(local: int, search: str | None = None):
    return _summary(local, search)


async def retrieve_credits_liquor(
    page: int,
    xpage: int,
    local: int,
    search: str | None = None,
    status: str | None = None,
):
    query = _filtered_query(local, search, status)
    total = sales_liquorDb.count_documents(query)
    credits = [
        sale_helper(sale)
        for sale in sales_liquorDb.find(query)
        .sort([("fechaVencimiento", ASCENDING), ("fechaVenta", DESCENDING)])
        .skip((page - 1) * xpage)
        .limit(xpage)
    ]
    return {
        "credits": credits,
        "total": total,
        "page": page,
        "xpage": xpage,
        "summary": _summary(local, search),
    }


async def retrieve_credit_liquor_by_id(credit_id: str, local: int):
    query = _base_query(local)
    query["$and"].append({"_id": _object_id(credit_id)})
    credit = sales_liquorDb.find_one(query)
    if credit is None:
        raise HTTPException(status_code=404, detail="Crédito no encontrado.")
    return sale_helper(credit)


async def add_credit_payment_liquor(credit_id: str, payment_data: dict):
    object_id = _object_id(credit_id)
    sale = sales_liquorDb.find_one({"_id": object_id})
    if sale is None:
        raise HTTPException(status_code=404, detail="Crédito no encontrado.")
    if sale.get("condicionPago") != "credito" and sale.get("estado") != "credito":
        raise HTTPException(status_code=409, detail="La venta no corresponde a un crédito.")

    payment = sale.get("pago", {})
    total = _money(payment.get("total", 0), "El total")
    previous_paid = _money(payment.get("pagado", 0), "El monto pagado")
    previous_balance = _money(
        payment.get("saldoPendiente", max(total - previous_paid, 0)),
        "El saldo pendiente",
    )
    amount = _money(payment_data.get("monto"), "El monto del abono")
    if amount <= 0:
        raise HTTPException(status_code=422, detail="El abono debe ser mayor que cero.")
    if previous_balance <= 0:
        raise HTTPException(status_code=409, detail="Esta deuda ya se encuentra pagada.")
    if amount > previous_balance:
        raise HTTPException(status_code=422, detail="El abono no puede superar el saldo pendiente.")

    new_paid = round(previous_paid + amount, 2)
    new_balance = round(previous_balance - amount, 2)
    payment_status = "pagado" if new_balance == 0 else "parcial"
    payment_record = {
        "id": str(ObjectId()),
        "monto": amount,
        "fecha": _payment_datetime(payment_data.get("fecha")),
        "metodo": str(payment_data.get("metodo") or "").lower(),
        "referencia": payment_data.get("referencia") or None,
        "observaciones": payment_data.get("observaciones") or None,
    }
    changes = {
        "pago.pagado": new_paid,
        "pago.saldoPendiente": new_balance,
        "pago.estadoPago": payment_status,
        "estado": "cancelado" if new_balance == 0 else "credito",
        "updated_at": datetime.now(timezone.utc),
    }
    if new_balance == 0:
        changes["fechaCancelacion"] = datetime.now(timezone.utc)

    paid_condition = (
        {"pago.pagado": previous_paid}
        if "pagado" in payment
        else {"pago.pagado": {"$exists": False}}
    )
    updated = sales_liquorDb.find_one_and_update(
        {"_id": object_id, **paid_condition},
        {"$set": changes, "$push": {"pago.pagos": payment_record}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="La deuda cambió mientras registrabas el pago. Actualiza e inténtalo nuevamente.",
        )
    return sale_helper(updated)
