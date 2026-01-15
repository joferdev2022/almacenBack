from bson import ObjectId
from fastapi import APIRouter, Depends
from typing import List
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from datetime import datetime


from app.services.seller_service import retrieve_sellers, add_seller, delete_seller_by_id, update_seller_by_id, get_seller_monthly_stats
from app.models.seller_model import sellerModel, ResponseSellerModel, ErrorResponseModel


router = APIRouter()

@router.get("/sellers", tags=["sellers"])
async def get_sellers(page: int = 1, xpage: int = 10, local: int = 1):
    
    
    
    sellers_list = await retrieve_sellers(page, xpage, local)
    
    # print(products_list)
    return ResponseSellerModel(sellers_list, "Lista de vendedores")

@router.post("/sellers", tags=["sellers"])
async def save_seller(seller_data: sellerModel):
    
    new_seller = jsonable_encoder(seller_data)
    seller_bd = await add_seller(new_seller)
    print(seller_bd)
    return "ok"

@router.put("/sellers/{id}", tags=["sellers"])
async def update_seller(id: str, seller_data: sellerModel):
    
    seller_update = jsonable_encoder(seller_data)
    result = await update_seller_by_id(id, seller_update)
    
    if result:
        return ResponseSellerModel("Vendedor ID: {} actualizado".format(id), "Vendedor actualizado de forma correcta")
        
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla actualizando los datos del Producto",
    )

@router.delete("/sellers/{id}", tags=["sellers"])
async def delete_seller(id: str):
    result = await delete_seller_by_id(id)
    if result:
        # return ResponseCustomerModel("Cliente ID: {} borrado".format(id), "Cliente borrado exitosamente")
        return "Vendedor borrado"
    # user = create_user(user_data)
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla borrando los datos del cliente",
    )
    

@router.get("/sellers/{seller_name}/monthly-stats", tags=["sellers"])
async def get_seller_monthly_stats_endpoint(seller_name: str, local: int = 1, year: int = None, month: int = None):
    if year is None or month is None:
        today = datetime.now()
        year = year or today.year
        month = month or today.month
    
    result = await get_seller_monthly_stats(seller_name, local, year, month)
    
    return {
        "vendedor": result["vendedor"],
        "mes": result["mes"],
        "año": result["año"],
        "totalVentas": result["totalVentas"],
        "montoTotal": result["montoTotal"],
        "ventas": result["ventas"],
        "comisionTotalEstimada": result["comisionTotalEstimada"],
        "code": 200,
        "message": f"Estadísticas de ventas de {seller_name} en {result['mes']}/{result['año']}"
    }

