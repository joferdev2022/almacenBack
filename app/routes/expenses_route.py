from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.models.expense_model import (
    ExpenseCategory, ExpenseModel, ExpensePaymentModel, ExpenseState,
    PaymentMethod, ResponseExpenseModel,
)
from app.services import expenses_service as service

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/options")
def expense_options(user: dict = Depends(service.get_expense_user)):
    return ResponseExpenseModel(service.get_expense_options(), "Opciones de gastos")


@router.get("/providers")
def expense_providers(search: str = Query(default="", max_length=100),
                      page: int = Query(default=1, ge=1),
                      xpage: int = Query(default=20, ge=1, le=50),
                      user: dict = Depends(service.get_expense_user)):
    return ResponseExpenseModel(service.retrieve_expense_providers(user, search, page, xpage),
                                "Proveedores del local")


@router.get("")
def get_expenses(page: int = Query(default=1, ge=1), xpage: int = Query(default=10, ge=1, le=100),
                 search: str = Query(default="", max_length=100),
                 fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None,
                 categoria: Optional[ExpenseCategory] = None, estado: Optional[ExpenseState] = None,
                 metodo_pago: Optional[PaymentMethod] = None,
                 local: Optional[int] = Query(default=None, ge=0),
                 user: dict = Depends(service.get_expense_user)):
    data = service.retrieve_expenses(user, page, xpage, search=search, fecha_desde=fecha_desde,
                                    fecha_hasta=fecha_hasta, categoria=categoria, estado=estado,
                                    metodo_pago=metodo_pago, local=local)
    return ResponseExpenseModel(data, "Lista de gastos")


@router.post("", status_code=201)
def save_expense(data: ExpenseModel, user: dict = Depends(service.get_expense_writer)):
    return ResponseExpenseModel(service.add_expense(data, user), "Gasto creado correctamente", 201)


@router.get("/{id}")
def get_expense(id: str, user: dict = Depends(service.get_expense_user)):
    return ResponseExpenseModel(service.retrieve_expense_by_id(id, user), "Detalle del gasto")


@router.put("/{id}")
def update_expense(id: str, data: ExpenseModel, user: dict = Depends(service.get_expense_writer)):
    return ResponseExpenseModel(service.update_expense_by_id(id, data, user), "Gasto actualizado correctamente")


@router.put("/{id}/pay")
def pay_expense(id: str, data: ExpensePaymentModel, user: dict = Depends(service.get_expense_writer)):
    return ResponseExpenseModel(service.pay_expense_by_id(id, data, user), "Gasto marcado como pagado")


@router.delete("/{id}")
def delete_expense(id: str, user: dict = Depends(service.get_expense_writer)):
    return ResponseExpenseModel(service.delete_expense_by_id(id, user), "Gasto eliminado correctamente")

