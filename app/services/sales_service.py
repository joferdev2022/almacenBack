from bson.objectid import ObjectId
from fastapi import HTTPException

from app.db.mongo import salesDb
from ..utils.helpers import sale_helper


async def retrieve_sales(page: int, xpage: int):
    sales = []
    totalSales = salesDb.count_documents({})
    
    if page < 1 or xpage < 1 or (page - 1) * xpage >= totalSales:
        raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
    skipSales = (page - 1) * xpage
    
    for sale in salesDb.find().skip(skipSales).limit(xpage):
        sale["id"] = str(sale["_id"])
        sales.append(sale_helper(sale))
    return {"total": totalSales, "sales": sales, "page": page, "xpage": xpage}


