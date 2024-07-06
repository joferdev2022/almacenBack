from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from datetime import datetime

class productModel(BaseModel):
    id: Optional[str] = Field(alias="_id") 
    nombre: str
    descripcion: Optional[str]=None
    categoria: str
    precioCompra: float
    precioVenta: float
    cantidadEnStock: int
    unidadDeMedida: str
    # ubicacionEnAlmacen: str
    proveedorId: str
    fechaDeCaducidad: Optional[datetime]=None
    # codigoDeBarras: str
    fechaDeCreacion: Optional[datetime] = Field(default_factory=datetime.now)
    # fechaDeActualizacion: Optional[datetime] = Field(default_factory=datetime.now)
    
    
    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
        }
        schema_extra = {
            "example": {
                "nombre": "Producto Ejemplo",
                "descripcion": "Una descripción detallada del producto.",
                "categoria": "Electrónica",
                "precioCompra": 150.00,
                "precioVenta": 200.00,
                "cantidadEnStock": 100,
                "unidadDeMedida": "unidad",
                # "ubicacionEnAlmacen": "A1-B2",
                "proveedorId": "60c72b2f9b1e8b4d5a7b9c9e",
                # "fechaDeCaducidad": "",
                # "codigoDeBarras": "1234567890123"
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