from fastapi import APIRouter, Depends
from typing import List

from app.services.sales_service import retrieve_sales
from app.models.sale_model import saleModel, ResponseSaleModel



router = APIRouter()


@router.get("/sales/", tags=["sales"])
async def get_sales(page: int = 1, xpage: int = 10):
    sales_list = await retrieve_sales(page, xpage)
    
    # print(sales_list)
    return ResponseSaleModel(sales_list, "Lista de ventas")








