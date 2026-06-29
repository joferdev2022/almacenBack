from bson.objectid import ObjectId
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.mongo import sales_liquorDb, products_liquorDb
from ..utils.helpers_liquor import sale_helper


async def retrieve_sales(page: int, xpage: int, local: int):
    total_sales = sales_liquorDb.count_documents({"local": local})

    if page < 1 or xpage < 1 or (page - 1) * xpage >= total_sales:
        raise HTTPException(
            status_code=400,
            detail="Parámetros de paginación inválidos."
        )

    skip_sales = (page - 1) * xpage

    sales = [
        sale_helper(sale)
        for sale in sales_liquorDb.find({"local": local})
                                 .sort("fechaVenta", -1)
                                 .skip(skip_sales)
                                 .limit(xpage)
    ]

    return {
        "total": total_sales,
        "sales": sales,
        "page": page,
        "xpage": xpage,
    }


async def get_sales_with_credit_state(page: int, xpage: int, local: int):
        sales = []
        totalSales = sales_liquorDb.count_documents({"local": local, "estado": "credito"})
        
        if totalSales == 0:
            return {"total": totalSales, "sales": sales, "page": page, "xpage": xpage}
        
        if page < 1 or xpage < 1 or (page - 1) * xpage >= totalSales:
            raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
        skipSales = (page - 1) * xpage
        
        for sale in sales_liquorDb.find({"local": local, "estado": "credito"}).skip(skipSales).limit(xpage):
            sales.append(sale_helper(sale))
        return {"total": totalSales, "sales": sales, "page": page, "xpage": xpage}


async def add_sale(sale_data: dict) -> dict:
    # assign new id
    sale_data["_id"] = ObjectId()

    # parse or set fechaVenta
    if "fechaVenta" in sale_data and sale_data["fechaVenta"]:
        if isinstance(sale_data["fechaVenta"], str):
            try:
                sale_data["fechaVenta"] = datetime.fromisoformat(sale_data["fechaVenta"].replace("Z", "+00:00"))
            except Exception:
                sale_data["fechaVenta"] = datetime.now(timezone.utc)
    else:
        sale_data["fechaVenta"] = datetime.now(timezone.utc)

    # calcular campos derivados por producto
    for item in sale_data.get("productos", []):
        cantidad = item.get("cantidad", 0)
        equivalencia = item.get("equivalenciaUnidades") or 1
        precio_compra = item.get("precioCompraUnitario", 0)
        precio_venta = item.get("precioVentaUnitario", 0)

        item["unidadesVendidas"] = cantidad * equivalencia
        item["subtotalCosto"] = cantidad * equivalencia * precio_compra
        item["subtotalVenta"] = cantidad * precio_venta

    # procesar pago: parsear fechas y calcular saldoPendiente
    if "pago" in sale_data and isinstance(sale_data["pago"], dict):
        pago = sale_data["pago"]

        # calcular saldoPendiente
        pago["saldoPendiente"] = pago.get("total", 0) - pago.get("pagado", 0)

        # parsear fechas dentro de pago.pagos
        for p in pago.get("pagos", []):
            fecha = p.get("fecha")
            if isinstance(fecha, str):
                try:
                    p["fecha"] = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
                except Exception:
                    p["fecha"] = None

    # insert sale
    sale = sales_liquorDb.insert_one(sale_data)
    new_sale = sales_liquorDb.find_one({"_id": sale.inserted_id})

    # update product stock; account for equivalenciaUnidades when present
    for item in sale_data.get("productos", []):
        producto_id = item.get("productoId")
        unidades = item.get("unidadesVendidas", 0)

        try:
            producto = products_liquorDb.find_one({"_id": ObjectId(producto_id)})
        except Exception:
            producto = None

        if producto:
            nuevo_stock = producto.get("cantidadEnStock", 0) - unidades
            products_liquorDb.update_one(
                {"_id": ObjectId(producto_id)},
                {"$set": {"cantidadEnStock": nuevo_stock}}
            )

    return sale_helper(new_sale)


async def update_sale_by_id(sale_id: str, new_data: dict):
    if "_id" in new_data:
        del new_data["_id"]
    sale = sales_liquorDb.find_one({"_id": ObjectId(sale_id)})
    print("esta imprimiendo la venta")
    print(sale)
    if sale:
        sales_liquorDb.update_one(
            {"_id": ObjectId(sale_id)}, {"$set": new_data}
        )
        return True
    return False


async def delete_sale_by_id(sale_id: str):
    sale = sales_liquorDb.find_one({"_id": ObjectId(sale_id)})
    if not sale:
        return False
    
    for item in sale["productos"]:
        producto_id = item["productoId"]
        unidades_vendidas = item.get("unidadesVendidas", item["cantidad"])
        producto = products_liquorDb.find_one({"_id": ObjectId(producto_id)})
        if producto:
            nuevo_stock = producto["cantidadEnStock"] + unidades_vendidas
            products_liquorDb.update_one(
                {"_id": ObjectId(producto_id)},
                {"$set": {"cantidadEnStock": nuevo_stock}}
            )
    filter = {"_id": ObjectId(sale_id)}
    
    result =  sales_liquorDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False


async def update_state_by_id(sale_id: str, new_state: str):
    
    tz = ZoneInfo("America/Lima")
    # now_local = datetime.now(tz)
    filter = {"_id": ObjectId(sale_id)}
    
    sale = sales_liquorDb.find_one(filter)
    
    if not sale:
        return False
    
    update_data = {"estado": new_state}

    # result =  sales_liquorDb.update_one(filter, {"$set": {"estado": new_state}})
    if sale.get("estado") == "credito" and new_state == "cancelado":
        update_data["fechaCancelacion"] = datetime.now(tz)
        # update_data["fechaCancelacion"] = datetime.now(timezone.utc)
    
    result = sales_liquorDb.update_one(filter, {"$set": update_data})
    if result.modified_count == 1:
        return True
    return False


async def update_payment_by_id(sale_id: str, new_payment: float):
    tz = ZoneInfo("America/Lima")
    filter = {"_id": ObjectId(sale_id)}
    
    sale = sales_liquorDb.find_one(filter)
    
    if not sale:
        return False
    
    pago = sale.get("pago", {})
    total_venta = pago.get("total", 0)
    pagado_anterior = pago.get("pagado", 0)
    
    # new_payment es el monto del nuevo abono
    nuevo_pagado = pagado_anterior + new_payment
    nuevo_saldo = total_venta - nuevo_pagado
    
    payment_record = {
        "monto": new_payment,
        "fecha": datetime.now(tz),
        "metodo": "efectivo"
    }
    
    update_data = {
        "pago.pagado": nuevo_pagado,
        "pago.saldoPendiente": nuevo_saldo
    }
    
    result = sales_liquorDb.update_one(
        filter, 
        {
            "$set": update_data,
            "$push": {"pago.pagos": payment_record}
        }
    )
    
    if result.modified_count == 1:
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



    sales_cursor = sales_liquorDb.find({
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
    pagos_parciales_hoy = 0
    
    for sale in sales_cursor:
        pago = sale.get("pago", {})
        total_ventas += pago.get("total", 0)
        for item in sale.get("productos", []):
            subtotal_venta = item.get("subtotalVenta", 0)
            subtotal_costo = item.get("subtotalCosto", 0)
            ganancia_neta += subtotal_venta - subtotal_costo
        numero_ventas += 1
    
    all_sales_cursor = sales_liquorDb.find({
        "local": local,
        "estado": "credito",
        "pago.pagos": {"$exists": True}
    })
    
    
    for sale in all_sales_cursor:
        pago_data = sale.get("pago", {})
        for pago_entry in pago_data.get("pagos", []):
            fecha_pago = pago_entry.get("fecha")
            if fecha_pago:
                # Convertir a UTC si es necesario
                if hasattr(fecha_pago, 'astimezone'):
                    fecha_pago_utc = fecha_pago.astimezone(ZoneInfo("UTC"))
                else:
                    fecha_pago_utc = fecha_pago
                
                if start_day_utc <= fecha_pago_utc < end_day_utc:
                    pagos_parciales_hoy += pago_entry.get("monto", 0)
    
    
    print(pagos_parciales_hoy)
    return {
        "ganancia_neta": ganancia_neta,
        "ventas_totales": total_ventas,
        "numero_ventas": numero_ventas,
        "pagos_parciales_hoy": pagos_parciales_hoy,
    }