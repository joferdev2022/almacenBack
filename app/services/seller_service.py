from bson.objectid import ObjectId
from fastapi import HTTPException
from datetime import datetime
from app.db.mongo import salesDb

from app.db.mongo import sellersDb
from ..utils.helpers import sale_helper, seller_helper

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

async def get_seller_monthly_stats(seller_name: str, local: int, year:int = None, month: int = None):
    
    start_date = datetime(year, month, 1)
    
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
        
    
    
    filter_query = {
        "nombreVendedor": {"$regex": f"^\\s*{seller_name}\\s*$", "$options": "i"},
        "local": local,
        "fechaVenta": {
            "$gte": start_date,
            "$lt": end_date
        }
    }
    
    total_ventas = salesDb.count_documents(filter_query)
    
    sales = []
    monto_total = 0
    comision_total_estimada = 0
    
    for sale in salesDb.find(filter_query):
        sale["id"] = str(sale["_id"])
        comision_venta = 0
        
        for producto in sale.get("productos", []):
            precio_venta = producto.get("precioUnitario", 0)
            precio_compra = producto.get("precioBuy", 0)
            cantidad = producto.get("cantidad", 1)
            
            ganancia = (precio_venta - precio_compra) * cantidad
            comision_producto = ganancia * 0.5
            comision_venta += comision_producto
            
        sale["comisionEstimada"] = round(comision_venta, 2)
        comision_total_estimada += comision_venta
        
        sales.append(sale_helper(sale))
        monto_total += sale.get("precioTotal", 0)
        
    return {
        "vendedor": seller_name,
        "mes": month,
        "año": year,
        "totalVentas": total_ventas,
        "montoTotal": monto_total,
        "comisionTotalEstimada": round(comision_total_estimada, 2),
        "ventas": sales
    }