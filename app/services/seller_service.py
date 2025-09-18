from bson.objectid import ObjectId
from fastapi import HTTPException

from app.db.mongo import sellersDb
from ..utils.helpers import seller_helper

async def retrieve_sellers(page: int, xpage: int, local:int):
    sellers = []
    totalSellers = sellersDb.count_documents({"local": local})
    print(totalSellers)
    
    if page < 1 or xpage < 1 or (page - 1) * xpage >= totalSellers:
        raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
    skipSellers = (page - 1) * xpage
    
    for seller in sellersDb.find({"local": local}).skip(skipSellers).limit(xpage):
        seller["id"] = str(seller["_id"])
        # print(seller)
        sellers.append(seller_helper(seller))
    return {"total": totalSellers, "sellers": sellers, "page": page, "xpage": xpage}

async def add_seller(seller_data: dict) -> dict:
    
    
    seller_data["_id"] = ObjectId()
    
    seller =  sellersDb.insert_one(seller_data)
    new_seller =  sellersDb.find_one({"_id": seller.inserted_id})
    
    return seller_helper(new_seller)

async def update_seller_by_id(seller_id: str, new_data: dict):
    if "_id" in new_data:
        del new_data["_id"]
    seller = sellersDb.find_one({"_id": ObjectId(seller_id)})
    print("esta imprimiendo el seller")
    print(seller)
    if seller:
        sellersDb.update_one(
            {"_id": ObjectId(seller_id)}, {"$set": new_data}
        )
        return True
    return False

async def delete_seller_by_id(seller_id: str):
    filter = {"_id": ObjectId(seller_id)}
    
    result =  sellersDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False