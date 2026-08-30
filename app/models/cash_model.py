"""Contratos de Caja física de almacen, independientes del login."""
from decimal import Decimal
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
JournalState = Literal["ABIERTA", "CERRADA"]
MovementDirection = Literal["INGRESO", "EGRESO"]
MovementType = Literal[
    "VENTA_EFECTIVO", "GASTO_EFECTIVO", "INGRESO_MANUAL", "RETIRO",
    "AJUSTE_ENTRADA", "AJUSTE_SALIDA", "RETIRO_CIERRE",
]
SourceType = Literal["VENTA", "GASTO", "MANUAL", "CIERRE"]


class CashOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    operacionId: UUID


class CashOpening(CashOperation):
    montoApertura: Money
    observaciones: Optional[str] = Field(default=None, max_length=1000)


class CashManualMovement(CashOperation):
    monto: PositiveMoney
    motivo: str = Field(min_length=3, max_length=250)
    observaciones: Optional[str] = Field(default=None, max_length=1000)


class CashClosing(CashOperation):
    montoContado: Money
    fondoSiguiente: Money
    version: int = Field(ge=0)
    observaciones: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_fund(self):
        if self.fondoSiguiente > self.montoContado:
            raise ValueError("El fondo siguiente no puede superar el efectivo contado.")
        return self


def cash_response(data, message="Consulta de caja", code=200):
    return {"data": data, "message": message, "code": code}
