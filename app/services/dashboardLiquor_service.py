from bson.objectid import ObjectId
from fastapi import HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
import calendar

from app.db.mongo import sales_liquorDb, products_liquorDb
from ..utils.helpers_liquor import sale_helper


def get_previous_month_filter(filtro_fecha):
    """Calcula el filtro de fechas equivalente para el mes anterior."""
    rango = filtro_fecha.get("fechaVenta", {})
    fecha_inicio = rango.get("$gte")
    fecha_fin = rango.get("$lt")

    if not fecha_inicio or not fecha_fin:
        return None

    # El mes anterior termina donde empieza el actual
    prev_fin = fecha_inicio

    # Retroceder un mes
    if fecha_inicio.month == 1:
        prev_inicio = fecha_inicio.replace(year=fecha_inicio.year - 1, month=12)
    else:
        prev_inicio = fecha_inicio.replace(month=fecha_inicio.month - 1)

    return {
        "fechaVenta": {
            "$gte": prev_inicio,
            "$lt": prev_fin
        }
    }


def calculate_percentage_change(current, previous):
    """Calcula el porcentaje de cambio entre el valor actual y el anterior."""
    if previous == 0:
        return None  # Sin datos previos, el frontend decide qué mostrar
    return round(((current - previous) / previous) * 100, 1)


async def get_sales_aggregates(filtro_fecha, local):
    """Retorna totalSales y AmountSales para un rango de fechas dado."""
    pipeline = [
        {"$match": {"$and": [filtro_fecha, {"local": local}]}},
        {
            "$group": {
                "_id": None,
                "totalSales": {"$sum": 1},
                "total": {"$sum": "$pago.total"}
            }
        }
    ]
    result = list(sales_liquorDb.aggregate(pipeline))
    return {
        "totalSales": result[0]["totalSales"] if result else 0,
        "AmountSales": result[0]["total"] if result else 0
    }


async def retrieve_dashboard_data(filtro_fecha, local):
    topProducts = await top_products(local)
    lowProducts = await low_stock_products(local)
    totalproducts = products_liquorDb.count_documents({"local": local})

    # Datos del mes actual
    current = await get_sales_aggregates(filtro_fecha, local)
    ingresoNeto = await get_monthly_net_income(filtro_fecha, local)

    # Datos del mes anterior para comparación
    prev_filter = get_previous_month_filter(filtro_fecha)
    comparacion = {"ingresoNeto": 0.0, "AmountSales": 0.0, "totalSales": 0.0}

    if prev_filter:
        prev = await get_sales_aggregates(prev_filter, local)
        prev_ingreso = await get_monthly_net_income(prev_filter, local)

        comparacion = {
            "ingresoNeto": calculate_percentage_change(ingresoNeto, prev_ingreso),
            "AmountSales": calculate_percentage_change(current["AmountSales"], prev["AmountSales"]),
            "totalSales": calculate_percentage_change(current["totalSales"], prev["totalSales"]),
        }

    return {
        "totalSales": current["totalSales"],
        "topProducts": topProducts,
        "lowProducts": lowProducts,
        "totalProducts": totalproducts,
        "AmountSales": current["AmountSales"],
        "ingresoNeto": ingresoNeto,
        "comparacion": comparacion
    }


async def get_monthly_net_income(filtro_fecha, local):
    """
    Calcula la utilidad realmente cobrada durante el periodo.

    La utilidad de una venta se reconoce proporcionalmente
    a cada pago recibido.
    """

    rango = filtro_fecha.get("fechaVenta", {})
    fecha_inicio = rango.get("$gte")
    fecha_fin = rango.get("$lt")

    utilidad_mes = 0

    cursor = sales_liquorDb.find({"local": local})

    for sale in cursor:

        pago = sale.get("pago", {})
        total_venta = pago.get("total", 0)

        if total_venta == 0:
            continue

        costo_total = sum(
            p.get("subtotalCosto", 0)
            for p in sale.get("productos", [])
        )

        utilidad_total = total_venta - costo_total

        porcentaje_utilidad = utilidad_total / total_venta

        for pago_realizado in pago.get("pagos", []):

            fecha_pago = pago_realizado.get("fecha")

            if fecha_inicio <= fecha_pago < fecha_fin:

                utilidad_mes += (
                    pago_realizado.get("monto", 0)
                    * porcentaje_utilidad
                )

    return round(utilidad_mes, 2)

async def top_products(local: int):
    pipeline = [
        {"$match": {"local": local}},
        {"$unwind": "$productos"},
        {
            "$group": {
                "_id": {"productoId": "$productos.productoId", "nombreProducto": "$productos.nombreProducto"},
                "cantidad_vendida": {"$sum": "$productos.cantidad"}
            }
        },
        {"$sort": {"cantidad_vendida": -1}},
        {"$limit": 10},
        {
            "$project": {
                "_id": 0,
                "productoId": "$_id.productoId",
                "nombreProducto": "$_id.nombreProducto",
                "cantidad_vendida": 1
            }
        }
    ]
    result = list(sales_liquorDb.aggregate(pipeline))
    productosTop = [
        {
            "productoId": item["productoId"],
            "nombreProducto": item["nombreProducto"],
            "cantidad_vendida": item["cantidad_vendida"]
        }
        for item in result
    ]
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
    result = list(products_liquorDb.aggregate(pipeline))
    lowStockProducts = [{"nombre": item["nombre"],
                  "categoria": item["categoria"],
                  "cantidadEnStock": item["cantidadEnStock"]}
                 for item in result]
    
    return lowStockProducts