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


async def add_sale(sale_data: dict) -> dict:
    sale_data["_id"] = ObjectId()
    sale =  salesDb.insert_one(sale_data)
    new_sale =  salesDb.find_one({"_id": sale.inserted_id})
    
    return sale_helper(new_sale)

async def update_sale_by_id(sale_id: str, new_data: dict):
    if "_id" in new_data:
        del new_data["_id"]
    sale = salesDb.find_one({"_id": ObjectId(sale_id)})
    print("esta imprimiendo la venta")
    print(sale)
    if sale:
        salesDb.update_one(
            {"_id": ObjectId(sale_id)}, {"$set": new_data}
        )
        return True
    return False

async def delete_sale_by_id(sale_id: str):
    filter = {"_id": ObjectId(sale_id)}
    
    result =  salesDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False
