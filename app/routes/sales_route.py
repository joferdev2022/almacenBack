from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.sales_model import saleModel, SalePaymentModel, ResponseSaleModel
from app.services import sales_service as service
from app.services.expenses_service import get_expense_user as get_current_user
from app.utils.operation_helpers import OperationReason, operation_key

router = APIRouter(prefix="/sales", tags=["sales"])


def get_sales_writer(user: dict = Depends(get_current_user)):
    if user.get("permissions") != 1:
        raise HTTPException(403, "No tienes permiso para modificar ventas.")
    return user


def scoped_local(local, user):
    if local is not None and local != user["local"]:
        raise HTTPException(403, "No puedes consultar ventas de otro local.")
    return user["local"]


@router.get("")
def get_sales(page: int = Query(1, ge=1), xpage: int = Query(10, ge=1, le=5000),
              local: Optional[int] = None, user: dict = Depends(get_current_user)):
    return ResponseSaleModel(service.retrieve_sales(page, xpage, scoped_local(local, user)), "Lista de ventas")


@router.get("/credits")
def get_credits(page: int = Query(1, ge=1), xpage: int = Query(10, ge=1, le=5000),
                local: Optional[int] = None, user: dict = Depends(get_current_user)):
    return ResponseSaleModel(service.get_sales_with_credit_state(page, xpage, scoped_local(local, user)), "Ventas a crédito")


@router.get("/summary/daily")
def summary(local: Optional[int] = None, user: dict = Depends(get_current_user)):
    return service.get_daily_Sales_summary(scoped_local(local, user))


@router.post("")
def create(data: saleModel, key: str = Depends(operation_key), user: dict = Depends(get_sales_writer)):
    return ResponseSaleModel(service.add_sale(data, user, key), "Venta registrada correctamente")


@router.put("/state/{id}")
def change_state(id: str, data: OperationReason, state: str, key: str = Depends(operation_key),
                 user: dict = Depends(get_sales_writer)):
    return ResponseSaleModel(service.update_state_by_id(id, state, data.motivo, user, key), "Cobro corregido")


@router.put("/payment/{id}")
def collect(id: str, data: SalePaymentModel, key: str = Depends(operation_key), user: dict = Depends(get_sales_writer)):
    return ResponseSaleModel(service.update_payment_by_id(id, data, user, key), "Cobro registrado correctamente")


@router.get("/{id}")
def detail(id: str, user: dict = Depends(get_current_user)):
    return ResponseSaleModel(service.get_sale_by_id(id, user), "Detalle de venta")


@router.put("/{id}")
def edit(id: str, data: saleModel, key: str = Depends(operation_key), user: dict = Depends(get_sales_writer)):
    return ResponseSaleModel(service.update_sale_by_id(id, data, user, key), "Venta actualizada correctamente")


@router.delete("/{id}")
def annul(id: str, data: OperationReason, key: str = Depends(operation_key), user: dict = Depends(get_sales_writer)):
    return ResponseSaleModel(service.delete_sale_by_id(id, user, key, data.motivo), "Venta anulada correctamente")
