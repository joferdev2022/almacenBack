from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.cash_model import (CashClosing, CashManualMovement, CashOpening,
    JournalState, MovementDirection, MovementType, SourceType, cash_response)
from app.models.payment_model import PaymentMethod
from app.services import cash_service as service
from app.services.expenses_service import get_expense_user as get_current_user

router = APIRouter(prefix="/cash", tags=["cash"])


def get_cash_writer(user: dict = Depends(get_current_user)):
    if user.get("permissions") != 1:
        raise HTTPException(403, "No tienes permiso para modificar la caja.")
    return user


@router.get("/current")
def current(user: dict = Depends(get_current_user)):
    return cash_response(service.current_cash(user))


@router.get("/history")
def history(page: int = Query(1, ge=1), xpage: int = Query(10, ge=1, le=100),
            fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None,
            estado: Optional[JournalState] = None, user: dict = Depends(get_current_user)):
    return cash_response(service.history(user, page, xpage, fecha_desde, fecha_hasta, estado))


@router.post("/open", status_code=201)
def open_cash(data: CashOpening, user: dict = Depends(get_cash_writer)):
    return cash_response(service.open_journal(data, user), "Caja abierta correctamente", 201)


@router.get("/{id}/movements")
def movements(id: str, page: int = Query(1, ge=1), xpage: int = Query(10, ge=1, le=100),
              fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None,
              tipo: Optional[MovementType] = None, naturaleza: Optional[MovementDirection] = None,
              origen_tipo: Optional[SourceType] = None, metodo_pago: Optional[PaymentMethod] = None,
              user: dict = Depends(get_current_user)):
    return cash_response(service.movements(id, user, page, xpage, fecha_desde, fecha_hasta,
        tipo, naturaleza, origen_tipo, metodo_pago))


@router.post("/{id}/income", status_code=201)
def income(id: str, data: CashManualMovement, user: dict = Depends(get_cash_writer)):
    return cash_response(service.manual_movement(id, data, user, "INGRESO"), "Ingreso registrado", 201)


@router.post("/{id}/withdrawal", status_code=201)
def withdrawal(id: str, data: CashManualMovement, user: dict = Depends(get_cash_writer)):
    return cash_response(service.manual_movement(id, data, user, "EGRESO"), "Retiro registrado", 201)


@router.post("/{id}/close")
def close_cash(id: str, data: CashClosing, user: dict = Depends(get_cash_writer)):
    return cash_response(service.close_journal(id, data, user), "Caja cerrada correctamente")


@router.get("/{id}")
def journal(id: str, user: dict = Depends(get_current_user)):
    return cash_response(service.get_journal(id, user))
