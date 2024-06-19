from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime


class topProductsModel(BaseModel):
    productoId: str
    cantidad: int
    precioUnitario: float
    productName: str
    
class lowStockModel(BaseModel):
    productoId: str
    cantidad: int
    precioUnitario: float
    productName: str

class dashboardModel(BaseModel):
    id: Optional[str] = Field(alias="_id")
    nombreCliente: str
    fechaVenta: str
    productos: List[topProductsModel]
    productos: List[lowStockModel]
    precioTotal: float
    estado: str = "pendiente"
    

        
def ResponseDashboardModel(data, message):
    
    # if "page" in data:
        
    #     return {
    #         "data": [data["sales"]],
    #         "total":data["total"],
    #         "code": 200,
    #         "message": message,
    #     }
    return {
            "data": data,
            "code": 200,
            "message": message,
        }


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}