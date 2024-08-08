from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime


class OrderItemModel(BaseModel):
    productoId: str
    cantidad: int
    precioUnitario: float
    productName: str

class saleModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    nombreCliente: str
    fechaVenta: Optional[datetime] = None
    productos: List[OrderItemModel]
    precioTotal: float
    estado: str = "pendiente"
    
    
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
                "nombreCliente": "jose lovaton",
                "fechaVenta": "2024-06-17 12:50:06.073606",
                "productos": [
                    {
                        "productoId": "60c72b2f9b1e8b4d5a7b9c9d",
                        "productName": "monitor 4k samsung",
                        "cantidad": 2,
                        "precioUnitario": 1500.00
                    },
                    {
                        "productoId": "60c72b2f9b1e8b4d5a7b9c9e",
                        "productName": "monitor 4k samsung",
                        "cantidad": 1,
                        "precioUnitario": 300.00
                    }
                ],
                "precioTotal": 3300.00,
                "estado": "pendiente",
            }
        }
        
def ResponseSaleModel(data, message):
    
    if "page" in data:
        
        return {
            "data": [data["sales"]],
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