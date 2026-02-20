from bson.objectid import ObjectId
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.mongo import salesDb, productsDb
from ..utils.helpers import sale_helper


async def retrieve_sales(page: int, xpage: int, local:int):
    sales = []
    totalSales = salesDb.count_documents({"local": local})
    
    if page < 1 or xpage < 1 or (page - 1) * xpage >= totalSales:
        raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
    skipSales = (page - 1) * xpage
    
    for sale in salesDb.find({"local": local}).skip(skipSales).limit(xpage):
        sale["id"] = str(sale["_id"])
        sale["precioTotalOriginal"] = sale.get("precioTotalOriginal", sale["precioTotal"])
        # print(sale)
        sales.append(sale_helper(sale))
    return {"total": totalSales, "sales": sales, "page": page, "xpage": xpage}

async def get_sales_with_credit_state(page: int, xpage: int, local: int):
        sales = []
        totalSales = salesDb.count_documents({"local": local, "estado": "credito"})
        
        if totalSales == 0:
            return {"total": totalSales, "sales": sales, "page": page, "xpage": xpage}
        
        if page < 1 or xpage < 1 or (page - 1) * xpage >= totalSales:
            raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
        skipSales = (page - 1) * xpage
        
        for sale in salesDb.find({"local": local, "estado": "credito"}).skip(skipSales).limit(xpage):
            sale["id"] = str(sale["_id"])
            sale["precioTotalOriginal"] = sale.get("precioTotalOriginal", sale["precioTotal"])
            sales.append(sale_helper(sale))
        return {"total": totalSales, "sales": sales, "page": page, "xpage": xpage}

async def add_sale(sale_data: dict) -> dict:
    
    # print(sale_data)
    
    sale_data["_id"] = ObjectId()
    
    sale_data["fechaVenta"] = datetime.now(timezone.utc)
    # sale_data["fechaVenta"] = datetime.now(timezone.utc)
    
    sale_data["precioTotalOriginal"] = sale_data["precioTotal"]
    # print(sale_data["fechaVenta"])
    # print(sale_data)
    
    sale =  salesDb.insert_one(sale_data)
    new_sale =  salesDb.find_one({"_id": sale.inserted_id})
    
    
    
    for item in sale_data["productos"]:
        # print(item)
        producto_id = item["productoId"]
        cantidad_vendida = item["cantidad"]
        producto = productsDb.find_one({"_id": ObjectId(producto_id)})
        if producto:
            nuevo_stock = producto["cantidadEnStock"] - cantidad_vendida
            productsDb.update_one(
                {"_id": ObjectId(producto_id)},
                {"$set": {"cantidadEnStock": nuevo_stock}}
            )
    
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
    sale = salesDb.find_one({"_id": ObjectId(sale_id)})
    if not sale:
        return False
    
    for item in sale["productos"]:
        producto_id = item["productoId"]
        cantidad_vendida = item["cantidad"]
        producto = productsDb.find_one({"_id": ObjectId(producto_id)})
        if producto:
            nuevo_stock = producto["cantidadEnStock"] + cantidad_vendida
            productsDb.update_one(
                {"_id": ObjectId(producto_id)},
                {"$set": {"cantidadEnStock": nuevo_stock}}
            )
    filter = {"_id": ObjectId(sale_id)}
    
    result =  salesDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False


async def update_state_by_id(sale_id: str, new_state: str):
    
    tz = ZoneInfo("America/Lima")
    # now_local = datetime.now(tz)
    filter = {"_id": ObjectId(sale_id)}
    
    sale = salesDb.find_one(filter)
    
    if not sale:
        return False
    
    update_data = {"estado": new_state}

    # result =  salesDb.update_one(filter, {"$set": {"estado": new_state}})
    if sale.get("estado") == "credito" and new_state == "cancelado":
        update_data["fechaCancelacion"] = datetime.now(tz)
        # update_data["fechaCancelacion"] = datetime.now(timezone.utc)
    
    result = salesDb.update_one(filter, {"$set": update_data})
    if result.modified_count == 1:
        return True
    return False

async def update_payment_by_id(sale_id: str, new_payment: float):
    filter = {"_id": ObjectId(sale_id)}
    
    sale = salesDb.find_one(filter)
    
    if not sale:
        return False
    
    if "precioTotalOriginal" not in sale:
        original_payment = sale["precioTotal"]
    else:
        original_payment = sale["precioTotalOriginal"]
    
    update_data = {
        "precioTotal": new_payment,
        "precioTotalOriginal": original_payment
    }
    
    result =  salesDb.update_one(filter, {"$set": update_data})
    if result.modified_count == 1:
        updated_sale = salesDb.find_one(filter)
        print(updated_sale)
        return True
    return False

async def get_daily_Sales_summary(local: int):
    tz = ZoneInfo("America/Lima")
    now_local = datetime.now(tz)
    # today = datetime.now(timezone.utc)
    
    # start_day = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    # end_day = start_day + timedelta(days=1)
    
    start_day_local = datetime(now_local.year, now_local.month, now_local.day, tzinfo=tz)
    end_day_local = start_day_local + timedelta(days=1)
    
    start_day_utc = start_day_local.astimezone(ZoneInfo("UTC"))
    end_day_utc = end_day_local.astimezone(ZoneInfo("UTC"))



    sales_cursor = salesDb.find({
        "local": local,
        "estado": "cancelado",
        "$or": [
            {"fechaVenta": {"$gte": start_day_utc, "$lt": end_day_utc}},
            {"fechaCancelacion": {"$gte": start_day_utc, "$lt": end_day_utc}}
        ]
        # "fechaVenta": {"$gte": start_day_utc, "$lt": end_day_utc}
    })
    
    total_ventas = 0
    ganancia_neta = 0
    numero_ventas = 0
    
    for sale in sales_cursor:
        total_ventas += sale.get("precioTotal", 0)
        # Suponiendo que cada producto tiene 'precioCompra' y 'cantidad'
        for item in sale.get("productos", []):
            print(item)
            precio_venta = item.get("precioUnitario", 0)
            precio_compra = item.get("precioBuy", 0)
            cantidad = item.get("cantidad", 0)
            ganancia_neta += (precio_venta - precio_compra) * cantidad
        numero_ventas += 1
    
    return {
        "ganancia_neta": ganancia_neta,
        "ventas_totales": total_ventas,
        "numero_ventas": numero_ventas
    }