"""Reglas y persistencia de Gastos, exclusivamente en almacen.expenses."""
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import get_args
from zoneinfo import ZoneInfo

import jwt
from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import TypeAdapter, ValidationError
from pymongo import DESCENDING, ReturnDocument

from app.db.mongo import authDb, expensesDb, providersDb
from app.models.expense_model import (
    ExpenseCategory, ExpenseModel, ExpensePaymentModel, ExpenseState,
    PaymentMethod, ReceiptType,
)
from app.services.auth_service import ALGORITHM, SECRET_KEY
from app.utils.helpers import expense_helper
from app.services import cash_service as cash
from app.services.cash_effects import capture_payment, revise_payment
from app.utils.cash_helpers import ZERO, money
from app.utils.operation_helpers import operation_hash, was_applied, stamp, ensure_active

LIMA = ZoneInfo("America/Lima")
expense_oauth = OAuth2PasswordBearer(tokenUrl="/api/auth")
_user_integer = TypeAdapter(int)


def get_expense_user(token: str = Depends(expense_oauth)):
    """Usa la identidad del login y los permisos actuales, sin caducidad temporal."""
    unauthorized = HTTPException(
        status_code=401, detail="No se pudo validar el acceso a Gastos.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Excepción temporal solicitada para desarrollo: Gastos no bloquea por
        # vencimiento. La firma, las claims requeridas y el usuario siguen validados.
        # Rehabilitar verify_exp antes de producción junto al manejo de renovación.
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub", "local"], "verify_exp": False})
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc
    if not isinstance(claims.get("sub"), str) or type(claims.get("local")) is not int:
        raise unauthorized
    user = authDb.find_one(
        {"username": claims["sub"]},
        {"_id": 1, "username": 1, "local": 1, "permissions": 1},
    )
    if user is None:
        raise unauthorized
    try:
        # El UserModel del login convierte estos campos de Mongo de texto a int.
        # Aplicar la misma conversión antes de comparar el local del token.
        user["local"] = _user_integer.validate_python(user.get("local"))
        user["permissions"] = _user_integer.validate_python(user.get("permissions"))
    except ValidationError as exc:
        raise unauthorized from exc
    if user["local"] < 0 or user["local"] != claims["local"]:
        raise unauthorized
    return user


def get_expense_writer(user: dict = Depends(get_expense_user)):
    if user.get("permissions") != 1:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar gastos.")
    return user


def _object_id(value: str, label="gasto"):
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail=f"El ID de {label} no es válido.")
    return ObjectId(value)


def _utc_day(value: date):
    return datetime.combine(value, time.min, tzinfo=LIMA).astimezone(timezone.utc)


def _scope(expense_id: str, user: dict):
    return {"_id": _object_id(expense_id), "local": user["local"]}


def get_expense_options():
    return {
        "categorias": get_args(ExpenseCategory), "estados": get_args(ExpenseState),
        "metodosPago": get_args(PaymentMethod), "tiposComprobante": get_args(ReceiptType),
    }


def retrieve_expense_providers(user: dict, search: str, page: int, xpage: int):
    query = {"local": user["local"]}
    if search.strip():
        query["nombreProvider"] = {"$regex": re.escape(search.strip()), "$options": "i"}
    total = providersDb.count_documents(query)
    providers = providersDb.find(query, {"nombreProvider": 1}).sort(
        [("nombreProvider", 1), ("_id", 1)]
    ).skip((page - 1) * xpage).limit(xpage)
    return {"items": [{"id": str(p["_id"]), "nombreProvider": p["nombreProvider"]}
                      for p in providers], "total": total, "page": page, "xpage": xpage}


def build_expense_query(user: dict, search="", fecha_desde=None, fecha_hasta=None,
                        categoria=None, estado=None, metodo_pago=None, local=None):
    if local is not None and local != user["local"]:
        raise HTTPException(status_code=403, detail="No puedes consultar gastos de otro local.")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(status_code=422, detail="La fecha desde no puede superar la fecha hasta.")
    query = {"local": user["local"], "anulado": {"$ne": True}}
    if fecha_desde or fecha_hasta:
        query["fecha"] = {}
        if fecha_desde:
            query["fecha"]["$gte"] = _utc_day(fecha_desde)
        if fecha_hasta:
            if fecha_hasta == date.max:
                raise HTTPException(status_code=422, detail="La fecha hasta está fuera de rango.")
            query["fecha"]["$lt"] = _utc_day(fecha_hasta + timedelta(days=1))
    for key, value in (("categoria", categoria), ("estado", estado), ("metodoPago", metodo_pago)):
        if value is not None:
            query[key] = value
    if search.strip():
        query["$or"] = [{key: {"$regex": re.escape(search.strip()), "$options": "i"}}
                        for key in ("descripcion", "proveedorNombre", "numeroComprobante")]
    return query


def retrieve_expenses(user: dict, page: int, xpage: int, **filters):
    query = build_expense_query(user, **filters)
    total = expensesDb.count_documents(query)
    cursor = expensesDb.find(query).sort([("fecha", DESCENDING), ("_id", DESCENDING)]).skip(
        (page - 1) * xpage
    ).limit(xpage)
    summary = list(expensesDb.aggregate([
        {"$match": query},
        {"$group": {
            "_id": None,
            "registrados": {"$sum": "$monto"},
            "pagados": {"$sum": {"$cond": [{"$eq": ["$estado", "PAGADO"]}, "$monto", 0]}},
            "pendientes": {"$sum": {"$cond": [{"$eq": ["$estado", "PENDIENTE"]}, "$monto", 0]}},
            "pagadosEfectivo": {"$sum": {"$cond": [{"$and": [
                {"$eq": ["$estado", "PAGADO"]}, {"$eq": ["$metodoPago", "EFECTIVO"]}
            ]}, "$monto", 0]}},
        }},
    ]))
    totals = summary[0] if summary else {}
    result_totals = {}
    for key in ("registrados", "pagados", "pendientes", "pagadosEfectivo"):
        value = totals.get(key, 0)
        result_totals[key] = float(value.to_decimal() if isinstance(value, Decimal128) else value)
    return {
        "expenses": [expense_helper(item) for item in cursor], "total": total,
        "page": page, "xpage": xpage, "resumen": result_totals,
    }


def retrieve_expense_by_id(expense_id: str, user: dict):
    expense = expensesDb.find_one(_scope(expense_id, user))
    if expense is None:
        raise HTTPException(status_code=404, detail="Gasto no encontrado.")
    return expense_helper(expense)


def _prepare_expense(data: ExpenseModel, user: dict, previous=None, session=None):
    result = data.model_dump()
    result["fecha"] = _utc_day(data.fecha)
    result["fechaPago"] = _utc_day(data.fechaPago) if data.fechaPago else None
    result["monto"] = Decimal128(data.monto)
    result["proveedorId"] = None
    result["proveedorNombre"] = None
    if data.proveedorId:
        provider_id = _object_id(data.proveedorId, "proveedor")
        provider = providersDb.find_one({"_id": provider_id, "local": user["local"]}, session=session)
        if provider:
            result["proveedorNombre"] = provider["nombreProvider"]
        elif previous and previous.get("proveedorId") == provider_id:
            # El catálogo permite borrar proveedores: conservar la referencia histórica.
            result["proveedorNombre"] = previous.get("proveedorNombre")
        else:
            raise HTTPException(status_code=422, detail="El proveedor no existe en tu local.")
        result["proveedorId"] = provider_id
    result["updated_at"] = datetime.now(timezone.utc)
    result["updated_by"] = user["_id"]
    return result


def _expense_effect(expense):
    return -money(expense["monto"]) if expense["estado"] == "PAGADO" else ZERO


def _expense_snapshot(expense):
    return {key: expense.get(key) for key in ("monto", "estado", "metodoPago", "fechaPago")}


def _write_expense(expense, session):
    expensesDb.update_one({"_id": expense["_id"], "local": expense["local"]},
        {"$set": {k: v for k, v in expense.items() if k != "_id"}}, session=session)
    return expense_helper(expense)


def add_expense(data: ExpenseModel, user: dict, key: str):
    digest = operation_hash("CREAR", data.model_dump(mode="json"))
    def write(session):
        previous = expensesDb.find_one({"local": user["local"], "operacionCreacion": key}, session=session)
        if previous:
            was_applied(previous, key, digest)
            return expense_helper(previous)
        expense = _prepare_expense(data, user, session=session)
        expense.update({"_id": ObjectId(), "local": user["local"], "usuarioId": user["_id"],
                        "created_at": expense["updated_at"], "operacionCreacion": key, "anulado": False})
        if expense["estado"] == "PAGADO":
            expense["pagoCaja"] = capture_payment(user, session, "GASTO", expense["_id"],
                f"GASTO:{expense['_id']}:{key}", _expense_effect(expense), expense.get("metodoPago"),
                expense.get("descripcion") or expense["categoria"])
        stamp(expense, key, digest, user, "CREAR")
        expensesDb.insert_one(expense, session=session)
        return expense_helper(expense)
    return cash.transaction(write)


def update_expense_by_id(expense_id: str, data: ExpenseModel, user: dict, key: str):
    query, digest = _scope(expense_id, user), operation_hash("EDITAR", data.model_dump(mode="json"))
    def write(session):
        expense = expensesDb.find_one(query, session=session)
        if expense is None:
            raise HTTPException(404, "Gasto no encontrado.")
        if was_applied(expense, key, digest):
            return expense_helper(expense)
        ensure_active(expense)
        before = _expense_snapshot(expense)
        was_paid = expense["estado"] == "PAGADO"
        expense.update(_prepare_expense(data, user, expense, session))
        changes = [{"antes": before, "despues": _expense_snapshot(expense)}]
        if not was_paid and expense["estado"] == "PAGADO":
            expense["pagoCaja"] = capture_payment(user, session, "GASTO", expense["_id"],
                f"GASTO:{expense['_id']}:{key}", _expense_effect(expense), expense.get("metodoPago"),
                expense.get("descripcion") or expense["categoria"])
        elif was_paid:
            expense["pagoCaja"], adjustment = revise_payment(expense.get("pagoCaja"), _expense_effect(expense),
                user, session, "GASTO", expense["_id"], f"GASTO:{expense['_id']}:{key}",
                "Corrección de gasto: " + (expense.get("descripcion") or expense["categoria"]),
                target_method=expense.get("metodoPago"))
            if adjustment:
                changes.append(adjustment)
        stamp(expense, key, digest, user, "EDITAR", changes=changes)
        return _write_expense(expense, session)
    return cash.transaction(write)


def pay_expense_by_id(expense_id: str, data: ExpensePaymentModel, user: dict, key: str):
    query, digest = _scope(expense_id, user), operation_hash("PAGAR", data.model_dump(mode="json"))
    def write(session):
        expense = expensesDb.find_one(query, session=session)
        if expense is None:
            raise HTTPException(404, "Gasto no encontrado.")
        if was_applied(expense, key, digest):
            return expense_helper(expense)
        ensure_active(expense)
        if expense["estado"] != "PENDIENTE":
            raise HTTPException(409, "El gasto ya no está pendiente. Actualiza el listado.")
        expense.update(estado="PAGADO", metodoPago=data.metodoPago, fechaPago=_utc_day(data.fechaPago))
        expense["pagoCaja"] = capture_payment(user, session, "GASTO", expense["_id"],
            f"GASTO:{expense['_id']}:{key}", _expense_effect(expense), expense.get("metodoPago"),
            expense.get("descripcion") or expense["categoria"])
        stamp(expense, key, digest, user, "PAGAR")
        return _write_expense(expense, session)
    return cash.transaction(write)


def delete_expense_by_id(expense_id: str, user: dict, key: str, reason: str):
    query, digest = _scope(expense_id, user), operation_hash("ANULAR", reason)
    def write(session):
        expense = expensesDb.find_one(query, session=session)
        if expense is None:
            raise HTTPException(404, "Gasto no encontrado.")
        if was_applied(expense, key, digest) or expense.get("anulado"):
            return expense_helper(expense)
        link, adjustment = revise_payment(expense.get("pagoCaja"), ZERO, user, session, "GASTO",
            expense["_id"], f"GASTO:{expense['_id']}:{key}", "Anulación de gasto: " + reason,
            annul=True, target_method=None)
        expense.update(anulado=True, anulado_at=datetime.now(timezone.utc), anulado_by=user["_id"],
                       motivoAnulacion=reason, pagoCaja=link)
        stamp(expense, key, digest, user, "ANULAR", reason, [adjustment] if adjustment else [])
        return _write_expense(expense, session)
    return cash.transaction(write)
