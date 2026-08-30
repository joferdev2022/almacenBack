from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.cash_model import PositiveMoney
from app.models.payment_model import PaymentMethod, normalize_payment


class OrderItemModel(BaseModel):
    productoId: str
    cantidad: int = Field(gt=0)
    precioUnitario: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    precioBuy: float = Field(default=0, ge=0, allow_inf_nan=False)
    productName: str


class saleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: Optional[str] = Field(None, alias="_id")
    nombreVendedor: str = Field(default="", max_length=150)
    nombreCliente: str = Field(default="", max_length=250)
    direccionCliente: str = Field(default="", max_length=500)
    fechaVenta: Optional[datetime] = None
    productos: List[OrderItemModel] = Field(min_length=1)
    precioTotal: float = Field(gt=0, allow_inf_nan=False)
    precioTotalOriginal: Optional[float] = None
    estado: Literal["cancelado", "credito", "pendiente"] = "cancelado"
    local: int = 0
    paymentMethod: Optional[str] = None

    @field_validator("paymentMethod")
    @classmethod
    def valid_method(cls, value):
        method = normalize_payment(value)
        if method == "TARJETA":
            raise ValueError("El pago con tarjeta no está disponible para Ventas.")
        return method.lower() if method else None

    @model_validator(mode="after")
    def paid_requires_method(self):
        if self.estado == "cancelado" and not self.paymentMethod:
            raise ValueError("Una venta pagada requiere método de pago.")
        return self


class SalePaymentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monto: PositiveMoney
    metodoPago: PaymentMethod
    fechaPago: date

    @field_validator("metodoPago")
    @classmethod
    def card_is_not_available(cls, value):
        if value == "TARJETA":
            raise ValueError("El pago con tarjeta no está disponible para Ventas.")
        return value


def ResponseSaleModel(data, message):
    if isinstance(data, dict) and "page" in data:
        return {"data": [data["sales"]], "total": data["total"],
                "page": data["page"], "xpage": data["xpage"], "code": 200, "message": message}
    return {"data": data, "code": 200, "message": message}


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}
