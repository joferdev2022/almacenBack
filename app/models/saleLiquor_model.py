from datetime import date, datetime
from typing import List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MetodoPagoLiquor = Literal[
    "efectivo",
    "yape",
    "plin",
    "transferencia",
    "tarjeta",
    "otro",
]


class ProductoVentaLiquorRequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    productoId: str
    skuId: Optional[str] = None
    cantidad: int = Field(gt=0)
    equivalenciaUnidades: Optional[int] = Field(default=1, gt=0)
    precioCompraUnitario: float = Field(default=0, ge=0, allow_inf_nan=False)
    precioVentaUnitario: float = Field(gt=0, allow_inf_nan=False)
    nombreProducto: Optional[str] = None
    marca: Optional[str] = None
    skuNombre: Optional[str] = None


class PagoEntradaLiquorRequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    monto: float = Field(gt=0, allow_inf_nan=False)
    fecha: Optional[datetime] = None
    metodo: MetodoPagoLiquor
    referencia: Optional[str] = Field(default=None, max_length=100)
    observaciones: Optional[str] = Field(default=None, max_length=500)


class PagoLiquorRequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tipo: str
    total: float = Field(gt=0, allow_inf_nan=False)
    pagado: float = Field(default=0, ge=0, allow_inf_nan=False)
    saldoPendiente: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    estadoPago: Optional[Literal["pendiente", "parcial", "pagado"]] = None
    pagos: List[PagoEntradaLiquorRequestModel] = Field(default_factory=list)

    @field_validator("tipo")
    @classmethod
    def normalize_type(cls, value: str):
        value = value.strip().lower()
        valid_values = {
            "efectivo",
            "yape",
            "plin",
            "transferencia",
            "tarjeta",
            "otro",
            "credito",
        }
        if value not in valid_values:
            raise ValueError("Método o condición de pago no válida.")
        return value


class ClienteCreditoLiquorModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=150)
    telefono: Optional[str] = Field(default=None, max_length=30)

    @field_validator("telefono")
    @classmethod
    def empty_phone_to_none(cls, value: Optional[str]):
        return value or None


class SaleLiquorRequestModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda value: value.isoformat()},
    )

    id: Optional[str] = Field(default=None, alias="_id")
    local: int = Field(ge=1)
    fechaVenta: Optional[datetime] = None
    estado: Literal["cancelado", "credito"] = "cancelado"
    condicionPago: Literal["contado", "credito"] = "contado"
    clienteCredito: Optional[ClienteCreditoLiquorModel] = None
    fechaVencimiento: Optional[date] = None
    observacionesCredito: Optional[str] = Field(default=None, max_length=500)
    pago: PagoLiquorRequestModel
    productos: List[ProductoVentaLiquorRequestModel] = Field(min_length=1)

    @field_validator("observacionesCredito")
    @classmethod
    def empty_observations_to_none(cls, value: Optional[str]):
        return value or None

    @model_validator(mode="after")
    def validate_credit_data(self):
        if self.condicionPago == "credito":
            if self.clienteCredito is None:
                raise ValueError("El cliente es obligatorio para una venta a crédito.")
            if self.fechaVencimiento is None:
                raise ValueError("La fecha de vencimiento es obligatoria para una venta a crédito.")
        return self


def ResponseSaleModel(data, message, code=200):
    if isinstance(data, dict) and "page" in data:
        return {
            "data": [data["sales"]],
            "total": data["total"],
            "page": data["page"],
            "xpage": data["xpage"],
            "code": code,
            "message": message,
        }
    return {"data": data, "code": code, "message": message}


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}
