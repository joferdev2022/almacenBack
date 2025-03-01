from fastapi import APIRouter, Depends
from typing import List
from bson import ObjectId
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.services.sales_service import retrieve_sales, add_sale, delete_sale_by_id, update_sale_by_id, update_state_by_id, update_payment_by_id, get_sales_with_credit_state
from app.models.sale_model import saleModel, ResponseSaleModel, ErrorResponseModel

# from app.services.products_service import retrieve_products, add_product, delete_product_by_id, update_product_by_id
# from app.models.product_model import productModel, ResponseProductModel, ErrorResponseModel


router = APIRouter()


@router.get("/sales", tags=["sales"])
async def get_sales(page: int = 1, xpage: int = 10, local: int = 1):
    sales_list = await retrieve_sales(page, xpage, local)
    
    # print(sales_list)
    return ResponseSaleModel(sales_list, "Lista de ventas")

@router.get("/sales/credits", tags=["sales"])
async def get_sales_with_credits(page: int = 1, xpage: int = 10, local: int = 1):
    sales_list = await get_sales_with_credit_state(page, xpage, local)
    
    # print(sales_list)
    return ResponseSaleModel(sales_list, "Lista de ventas a credito")

@router.post("/sales", tags=["sales"])
async def save_sale(sale_data: saleModel):
    
    new_sale = jsonable_encoder(sale_data)
    sale_bd = await add_sale(new_sale)
    print(sale_bd)
    return "ok"
    # return ResponseCustomerModel("Cliente creado de forma correcta")
    
@router.put("/sales/{id}", tags=["sales"])
async def update_sale(id: str, sale_data: saleModel):
    
    sale_update = jsonable_encoder(sale_data)
    result = await update_sale_by_id(id, sale_update)
    
    if result:
        return ResponseSaleModel("Venta ID: {} actualizado".format(id), "Venta actualizado de forma correcta")
        
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla actualizando los datos de la venta",
    )

@router.put("/sales/state/{id}", tags=["sales"])
async def update_state_sale(id: str, state: str):
    # sale_update = {"estado": state}
    result = await update_state_by_id(id, state)
    
    if result:
        return ResponseSaleModel("Venta ID: {} actualizado".format(id), "Venta actualizada de forma correcta")
        
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla actualizando los datos de la venta",
    )
    
@router.put("/sales/payment/{id}", tags=["sales"])
async def update_state_sale(id: str, payment: float):
    # sale_update = {"estado": state}
    result = await update_payment_by_id(id, payment)
    
    if result:
        return ResponseSaleModel("Venta ID: {} actualizado".format(id), "Venta actualizada de forma correcta")
        
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla actualizando los datos de la venta",
    )

@router.delete("/sales/{id}", tags=["sales"])
async def delete_sale(id: str):
    result = await delete_sale_by_id(id)
    if result:
        # return ResponseCustomerModel("Cliente ID: {} borrado".format(id), "Cliente borrado exitosamente")
        return "venta borrada"
    # user = create_user(user_data)
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla borrando los datos de la venta",
    )








