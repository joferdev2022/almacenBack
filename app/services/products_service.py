from bson.objectid import ObjectId
from fastapi import HTTPException

from app.db.mongo import productsDb
from ..utils.helpers import product_helper


async def retrieve_products(page: int, xpage: int):
    products = []
    totalProducts = productsDb.count_documents({})
    
    if page < 1 or xpage < 1 or (page - 1) * xpage >= totalProducts:
        raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
    skipProducts = (page - 1) * xpage
    
    for product in productsDb.find().skip(skipProducts).limit(xpage):
        product["id"] = str(product["_id"])
        products.append(product_helper(product))
    return {"total": totalProducts, "products": products, "page": page, "xpage": xpage}

async def add_product(product_data: dict) -> dict:
    product_data["_id"] = ObjectId()
    product =  productsDb.insert_one(product_data)
    new_product =  productsDb.find_one({"_id": product.inserted_id})
    
    return product_helper(new_product)

async def delete_product_by_id(product_id: str):
    filter = {"_id": ObjectId(product_id)}
    
    result =  productsDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False