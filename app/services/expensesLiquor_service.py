from datetime import datetime
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import HTTPException
from pymongo import DESCENDING, ReturnDocument

from app.db.mongo import expenses_liquorDb
from app.utils.helpers_liquor import expense_helper


def _parse_expense_date(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="La fecha del gasto no tiene un formato válido.",
            ) from exc

    if not isinstance(value, datetime):
        raise HTTPException(
            status_code=400,
            detail="La fecha del gasto es obligatoria.",
        )

    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("America/Lima"))

    return value.astimezone(ZoneInfo("UTC"))


def _get_object_id(expense_id: str):
    if not ObjectId.is_valid(expense_id):
        raise HTTPException(status_code=400, detail="El ID del gasto no es válido.")
    return ObjectId(expense_id)


def _prepare_expense_data(expense_data: dict):
    expense_data = expense_data.copy()
    expense_data.pop("_id", None)
    expense_data.pop("id", None)
    expense_data["fecha"] = _parse_expense_date(expense_data.get("fecha"))
    return expense_data


async def retrieve_expenses(page: int, xpage: int, local: int):
    if page < 1 or xpage < 1:
        raise HTTPException(
            status_code=400,
            detail="Parámetros de paginación inválidos.",
        )

    query = {"local": local}
    total_expenses = expenses_liquorDb.count_documents(query)

    if total_expenses == 0:
        return {
            "total": 0,
            "expenses": [],
            "page": page,
            "xpage": xpage,
        }

    skip_expenses = (page - 1) * xpage
    if skip_expenses >= total_expenses:
        raise HTTPException(
            status_code=400,
            detail="La página solicitada no contiene gastos.",
        )

    cursor = (
        expenses_liquorDb.find(query)
        .sort([("fecha", DESCENDING), ("_id", DESCENDING)])
        .skip(skip_expenses)
        .limit(xpage)
    )
    expenses = [expense_helper(expense) for expense in cursor]

    return {
        "total": total_expenses,
        "expenses": expenses,
        "page": page,
        "xpage": xpage,
    }


async def add_expense(expense_data: dict):
    expense_data = _prepare_expense_data(expense_data)
    expense_data["_id"] = ObjectId()

    result = expenses_liquorDb.insert_one(expense_data)
    new_expense = expenses_liquorDb.find_one({"_id": result.inserted_id})
    return expense_helper(new_expense)


async def update_expense_by_id(expense_id: str, expense_data: dict):
    object_id = _get_object_id(expense_id)
    expense_data = _prepare_expense_data(expense_data)

    updated_expense = expenses_liquorDb.find_one_and_update(
        {"_id": object_id},
        {"$set": expense_data},
        return_document=ReturnDocument.AFTER,
    )
    if updated_expense is None:
        raise HTTPException(status_code=404, detail="Gasto no encontrado.")

    return expense_helper(updated_expense)


async def delete_expense_by_id(expense_id: str):
    object_id = _get_object_id(expense_id)
    deleted_expense = expenses_liquorDb.find_one_and_delete({"_id": object_id})

    if deleted_expense is None:
        raise HTTPException(status_code=404, detail="Gasto no encontrado.")

    return expense_helper(deleted_expense)
