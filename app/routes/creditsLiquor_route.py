from typing import Literal, Optional

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder

from app.models.creditLiquor_model import AbonoCreditoLiquorModel, ResponseCreditLiquorModel
from app.services.creditsLiquor_service import (
    add_credit_payment_liquor,
    retrieve_credit_liquor_by_id,
    retrieve_credit_summary_liquor,
    retrieve_credits_liquor,
)


router = APIRouter()


@router.get("/creditsliquor", tags=["liquor credits"])
async def get_credits_liquor(
    page: int = Query(default=1, ge=1),
    xpage: int = Query(default=10, ge=1, le=5000),
    local: int = Query(default=1, ge=1),
    search: Optional[str] = Query(default=None, max_length=150),
    status: Optional[Literal["pendiente", "parcial", "pagado", "vencido"]] = None,
):
    credits = await retrieve_credits_liquor(page, xpage, local, search, status)
    return ResponseCreditLiquorModel(credits, "Lista de créditos")


@router.get("/creditsliquor/summary", tags=["liquor credits"])
async def get_credit_summary_liquor(
    local: int = Query(default=1, ge=1),
    search: Optional[str] = Query(default=None, max_length=150),
):
    summary = await retrieve_credit_summary_liquor(local, search)
    return ResponseCreditLiquorModel(summary, "Resumen de créditos")


@router.get("/creditsliquor/{id}", tags=["liquor credits"])
async def get_credit_liquor(id: str, local: int = Query(default=1, ge=1)):
    credit = await retrieve_credit_liquor_by_id(id, local)
    return ResponseCreditLiquorModel(credit, "Detalle del crédito")


@router.post("/creditsliquor/{id}/payments", tags=["liquor credits"])
async def register_credit_payment_liquor(id: str, payment: AbonoCreditoLiquorModel):
    credit = await add_credit_payment_liquor(id, jsonable_encoder(payment))
    return ResponseCreditLiquorModel(credit, "Abono registrado correctamente")
