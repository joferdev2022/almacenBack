from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExpenseLiquorModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "fecha": "2026-07-28T10:00:00-05:00",
                "categoria": "Publicidad",
                "descripcion": "Campaña de Google Ads",
                "proveedor": "Google Ads",
                "metodoPago": "Tarjeta",
                "comprobante": None,
                "estado": "pagado",
                "monto": 150.00,
                "local": 1,
                "observaciones": "Campaña correspondiente al mes de julio",
            }
        },
    )

    id: Optional[str] = Field(default=None, alias="_id")
    fecha: datetime
    categoria: str = Field(min_length=1)
    descripcion: Optional[str] = None
    proveedor: Optional[str] = None
    metodoPago: str = Field(min_length=1)
    comprobante: Optional[str] = None
    estado: str = Field(min_length=1)
    monto: float = Field(gt=0)
    local: int = Field(default=1, ge=1)
    observaciones: Optional[str] = None


def ResponseExpenseModel(data, message, code=200):
    if "page" in data:
        return {
            "data": [data["expenses"]],
            "total": data["total"],
            "page": data["page"],
            "xpage": data["xpage"],
            "code": code,
            "message": message,
        }

    return {
        "data": data,
        "code": code,
        "message": message,
    }


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}
