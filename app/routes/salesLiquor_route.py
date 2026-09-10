from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder

from app.models.saleLiquor_model import ResponseSaleModel, SaleLiquorRequestModel
from app.services.salesLiquor_service import (
    add_sale,
    delete_sale_by_id,
    get_daily_Sales_summary,
    retrieve_sales,
)


router = APIRouter()


@router.get("/salesliquor", tags=["liquor sales"])
async def get_sales(
    page: int = Query(default=1, ge=1),
    xpage: int = Query(default=10, ge=1, le=5000),
    local: int = Query(default=1, ge=1),
):
    sales = await retrieve_sales(page, xpage, local)
    return ResponseSaleModel(sales, "Lista de ventas")


@router.get("/salesliquor/summary/daily", tags=["liquor sales"])
async def daily_sales_summary(local: int = Query(default=1, ge=1)):
    return await get_daily_Sales_summary(local)


@router.post("/salesliquor", status_code=201, tags=["liquor sales"])
async def save_sale(sale_data: SaleLiquorRequestModel):
    sale = await add_sale(jsonable_encoder(sale_data))
    return ResponseSaleModel(sale, "Venta creada correctamente", code=201)


@router.delete("/salesliquor/{id}", tags=["liquor sales"])
async def delete_sale(id: str):
    deleted_sale = await delete_sale_by_id(id)
    return ResponseSaleModel(deleted_sale, "Venta eliminada correctamente")
