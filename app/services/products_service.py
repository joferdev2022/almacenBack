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