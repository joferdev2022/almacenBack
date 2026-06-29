from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime


class SkuModel(BaseModel):
    skuId: str
    nombre: str
    equivalenciaUnidades: int
    precioVenta: float


class productModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    nombre: str
    descripcion: Optional[str] = None
    categoria: str
    marca: Optional[str] = None
    contenido: Optional[float] = None
    unidadContenido: Optional[str] = None
    presentacion: Optional[str] = None
    barcode: Optional[str] = None
    precioCompra: float
    sku: List[SkuModel] = []
    cantidadEnStock: int
    proveedorId: Optional[str] = None
    fechaDeCaducidad: Optional[datetime] = None
    fechaDeCreacion: Optional[datetime] = Field(default_factory=datetime.now)
    local: int = 0

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
        }
        schema_extra = {
            "example": {
                "nombre": "Russkaya Pink",
                "descripcion": "",
                "categoria": "ron",
                "marca": "russkaya",
                "contenido": 750,
                "unidadContenido": "ml",
                "presentacion": "botella",
                "barcode": "",
                "precioCompra": 2130,
                "sku": [
                    {
                        "skuId": "unidad",
                        "nombre": "Unidad",
                        "equivalenciaUnidades": 1,
                        "precioVenta": 2800
                    }
                ],
                "cantidadEnStock": 3,
                "proveedorId": None,
                "fechaDeCaducidad": None,
                "local": 1
            }
        }
        
def ResponseProductModel(data, message):
    
    if "page" in data:
        
        return {
            "data": [data["products"]],
            "total":data["total"],
            "page":data["page"],
            "xpage":data["xpage"],
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