"""Contratos de Gastos de almacen; no comparten datos con licoreria."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExpenseCategory = Literal[
    "Servicios", "Transporte", "Alimentación", "Mantenimiento",
    "Compras menores", "Alquiler", "Personal", "Impuestos", "Otros",
]
ExpenseState = Literal["PAGADO", "PENDIENTE"]
PaymentMethod = Literal["EFECTIVO", "YAPE", "PLIN", "TRANSFERENCIA", "TARJETA", "OTRO"]
ReceiptType = Literal["BOLETA", "FACTURA", "RECIBO", "SIN_COMPROBANTE", "OTRO"]


class ExpenseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    fecha: date
    categoria: ExpenseCategory
    descripcion: Optional[str] = Field(default=None, max_length=250)
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    estado: ExpenseState
    metodoPago: Optional[PaymentMethod] = None
    fechaPago: Optional[date] = None
    proveedorId: Optional[str] = None
    tipoComprobante: ReceiptType = "SIN_COMPROBANTE"
    numeroComprobante: Optional[str] = Field(default=None, max_length=100)
    observaciones: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_payment(self):
        if self.estado == "PAGADO":
            if self.metodoPago is None:
                raise ValueError("El método de pago es obligatorio para un gasto pagado.")
            self.fechaPago = self.fechaPago or self.fecha
        elif self.fechaPago is not None:
            raise ValueError("Un gasto pendiente no puede tener fecha de pago.")
        return self


class ExpensePaymentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metodoPago: PaymentMethod
    fechaPago: date


def ResponseExpenseModel(data, message, code=200):
    if isinstance(data, dict) and "expenses" in data and "page" in data:
        return {
            "data": [data["expenses"]], "total": data["total"],
            "page": data["page"], "xpage": data["xpage"],
            "resumen": data["resumen"], "code": code, "message": message,
        }
    return {"data": data, "code": code, "message": message}
