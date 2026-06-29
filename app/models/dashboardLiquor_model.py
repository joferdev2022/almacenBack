from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime


class topProductsModel(BaseModel):
    productoId: str
    nombreProducto: str
    cantidad_vendida: int

class lowStockModel(BaseModel):
    nombre: str
    categoria: str
    cantidadEnStock: int

class dashboardModel(BaseModel):
    totalSales: int
    AmountSales: int
    ingresoNeto: int
    totalProducts: int
    topProducts: List[topProductsModel]
    lowProducts: List[lowStockModel]
    

        
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