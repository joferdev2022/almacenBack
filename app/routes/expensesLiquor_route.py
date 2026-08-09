from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder

from app.models.expenseLiquor_model import ExpenseLiquorModel, ResponseExpenseModel
from app.services.expensesLiquor_service import (
    add_expense,
    delete_expense_by_id,
    retrieve_expenses,
    update_expense_by_id,
)


router = APIRouter()


@router.get("/expensesliquor", tags=["liquor expenses"])
async def get_expenses(
    page: int = Query(default=1, ge=1),
    xpage: int = Query(default=10, ge=1, le=100),
    local: int = Query(default=1, ge=1),
):
    expenses = await retrieve_expenses(page, xpage, local)
    return ResponseExpenseModel(expenses, "Lista de gastos")


@router.post("/expensesliquor", status_code=201, tags=["liquor expenses"])
async def save_expense(expense_data: ExpenseLiquorModel):
    new_expense = jsonable_encoder(expense_data)
    expense = await add_expense(new_expense)
    return ResponseExpenseModel(expense, "Gasto creado correctamente", code=201)


@router.put("/expensesliquor/{id}", tags=["liquor expenses"])
async def update_expense(id: str, expense_data: ExpenseLiquorModel):
    expense_update = jsonable_encoder(expense_data)
    expense = await update_expense_by_id(id, expense_update)
    return ResponseExpenseModel(expense, "Gasto actualizado correctamente")


@router.delete("/expensesliquor/{id}", tags=["liquor expenses"])
async def delete_expense(id: str):
    expense = await delete_expense_by_id(id)
    return ResponseExpenseModel(expense, "Gasto eliminado correctamente")
