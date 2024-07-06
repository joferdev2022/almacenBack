from bson import ObjectId
from fastapi import APIRouter, Depends
from typing import List
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.services.products_service import retrieve_products, add_product, delete_product_by_id
from app.models.product_model import productModel, ResponseProductModel, ErrorResponseModel



router = APIRouter()


@router.get("/products", tags=["products"])
async def get_products(page: int = 1, xpage: int = 10):
    products_list = await retrieve_products(page, xpage)
    
    # print(products_list)
    return ResponseProductModel(products_list, "Lista de productos")

@router.post("/products", tags=["products"])
async def save_product(product_data: productModel):
    
    new_product = jsonable_encoder(product_data)
    product_bd = await add_product(new_product)
    print(product_bd)
    return "ok"
    # return ResponseCustomerModel("Cliente creado de forma correcta")

@router.delete("/products/{id}", tags=["products"])
async def delete_product(id: str):
    result = await delete_product_by_id(id)
    if result:
        # return ResponseCustomerModel("Cliente ID: {} borrado".format(id), "Cliente borrado exitosamente")
        return "cliente borrado"
    # user = create_user(user_data)
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla borrando los datos del cliente",
    )