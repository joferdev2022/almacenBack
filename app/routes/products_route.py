from fastapi import APIRouter, Depends
from typing import List

from app.services.products_service import retrieve_products
from app.models.product_model import productModel, ResponseProductModel



router = APIRouter()


@router.get("/products/", tags=["products"])
async def get_products(page: int = 1, xpage: int = 10):
    products_list = await retrieve_products(page, xpage)
    
    # print(products_list)
    return ResponseProductModel(products_list, "Lista de productos")

