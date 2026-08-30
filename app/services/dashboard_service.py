from bson.objectid import ObjectId
from fastapi import HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
import calendar

from app.db.mongo import salesDb, productsDb
from ..utils.helpers import sale_helper


async def retrieve_dashboard_data(filtro_fecha, local):
    topProducts = await top_products(local)
    lowProducts = await low_stock_products(local)
    # totalSales = salesDb.count_documents({})
    totalproducts = productsDb.count_documents({"local": local})
    
    # AmountSales = 0
    
    # prueba = await top_products()
    
    pipeline = [
        
        {"$match": {"$and": [filtro_fecha, {"local": local}, {"anulado": {"$ne": True}}]}},
        {
            "$group": {
                "_id": None,
                "totalSales": {"$sum": 1},
                "total": {"$sum": "$precioTotal"}
            }
        }
    ]
    
      
    result = list(salesDb.aggregate(pipeline))
    AmountSales = result[0]["total"] if result else 0
    totalSales = result[0]["totalSales"] if result else 0
    monthlyProfit = await get_monthly_net_profit(filtro_fecha, local)

    
    return {"totalSales": totalSales, "topProducts": topProducts, "lowProducts": lowProducts, "totalProducts": totalproducts, "AmountSales": AmountSales, "monthlyProfit": monthlyProfit}


async def get_monthly_net_profit(filtro_fecha, local):
    sales_cursor = salesDb.find({
        "$and": [filtro_fecha, {"local": local}, {"estado": "cancelado"}, {"anulado": {"$ne": True}}]
    })
    
    ganancia_neta = 0
    
    for sale in sales_cursor:
        for item in sale.get("productos", []):
            precio_venta = item.get("precioUnitario", 0)
            precio_compra = item.get("precioBuy", 0)
            cantidad = item.get("cantidad", 0)
            ganancia_neta += (precio_venta - precio_compra) * cantidad
    
    return ganancia_neta

async def top_products(local: int):
    pipeline = [
        {"$match": {"local": local, "anulado": {"$ne": True}}},
        {"$unwind": "$productos"},
        {
            "$group": {
                "_id": {"productoId": "$productos.productoId", "productName": "$productos.productName"},
                "cantidad_vendida": {"$sum": "$productos.cantidad"}
            }
        },
        {"$sort": {"cantidad_vendida": -1}},
        {"$limit": 10},
        {
            "$project": {
                "_id": 0,
                "productoId": "$_id.productoId",
                "productName": "$_id.productName",
                "cantidad_vendida": 1
            }
        }
    ]
    result = list(salesDb.aggregate(pipeline))
    productosTop = [{"productoId": item["productoId"], "productName": item["productName"], "cantidad_vendida": item["cantidad_vendida"]} for item in result]
    # print(productos)
    return productosTop

async def low_stock_products(local: int):
    pipeline = [
        {"$match": {"local": local}},
        {"$sort": {"cantidadEnStock": 1}},
        {"$limit": 10},
        {
            "$project": {
                "_id": 0,
                "nombre": 1,
                "categoria": 1,
                "cantidadEnStock": 1
            }
        }
    ]
    result = list(productsDb.aggregate(pipeline))
    lowStockProducts = [{"nombre": item["nombre"],
                  "categoria": item["categoria"],
                  "cantidadEnStock": item["cantidadEnStock"]}
                 for item in result]
    
    return lowStockProducts