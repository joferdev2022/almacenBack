from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.saleLiquor_model import MetodoPagoLiquor


class AbonoCreditoLiquorModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    monto: float = Field(gt=0, allow_inf_nan=False)
    metodo: MetodoPagoLiquor
    fecha: Optional[datetime] = None
    referencia: Optional[str] = Field(default=None, max_length=100)
    observaciones: Optional[str] = Field(default=None, max_length=500)

    @field_validator("referencia", "observaciones")
    @classmethod
    def empty_text_to_none(cls, value: Optional[str]):
        return value or None


def ResponseCreditLiquorModel(data, message, code=200):
    if isinstance(data, dict) and "page" in data:
        return {
            "data": [data["credits"]],
            "total": data["total"],
            "page": data["page"],
            "xpage": data["xpage"],
            "summary": data.get("summary", {}),
            "code": code,
            "message": message,
        }
    return {"data": data, "code": code, "message": message}
