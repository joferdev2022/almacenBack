from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime


class ProductoVentaRequestModel(BaseModel):
    productoId: str
    skuId: Optional[str]
    cantidad: int
    equivalenciaUnidades: Optional[int]
    precioCompraUnitario: float
    precioVentaUnitario: float
    nombreProducto: Optional[str]
    marca: Optional[str]
    skuNombre: Optional[str]


class PagoEntradaRequestModel(BaseModel):
    monto: float
    fecha: Optional[datetime] = None
    metodo: Optional[str] = None


class PagoRequestModel(BaseModel):
    tipo: str
    total: float
    pagado: float
    pagos: List[PagoEntradaRequestModel]


class SaleLiquorRequestModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    local: int
    fechaVenta: Optional[datetime] = None
    estado: str
    pago: PagoRequestModel
    productos: List[ProductoVentaRequestModel]

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        orm_mode = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
        }
        schema_extra = {
            "example": {
                "local": 1,
                "fechaVenta": "2026-06-28T15:18:30.479Z",
                "estado": "cancelado",
                "pago": {
                    "tipo": "yape",
                    "total": 3400,
                    "pagado": 3400,
                    "pagos": [
                        {
                            "monto": 3400,
                            "fecha": "2026-06-28T15:18:30.479Z",
                            "metodo": "yape"
                        }
                    ]
                },
                "productos": [
                    {
                        "productoId": "6a3eaf628330a86ad5eb8824",
                        "skuId": "cristal_sixpack",
                        "cantidad": 1,
                        "equivalenciaUnidades": 6,
                        "precioCompraUnitario": 420,
                        "precioVentaUnitario": 3400,
                        "nombreProducto": "cristal",
                        "marca": "cristal",
                        "skuNombre": "Six Pack x6"
                    }
                ]
            }
        }


def ResponseSaleModel(data, message):
    if "page" in data:
        return {
            "data": [data["sales"]],
            "total": data["total"],
            "page": data["page"],
            "xpage": data["xpage"],
            "code": 200,
            "message": message,
        }
    return {
        "data": data,
        "code": 200,
        "message": message,
    }


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}
