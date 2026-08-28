from datetime import datetime
from zoneinfo import ZoneInfo

def product_helper(products) -> dict:
    return {
        "id": str(products["_id"]),
        "nombre": products["nombre"],
        "descripcion": products["descripcion"],
        "categoria": products["categoria"],
        "precioCompra": products["precioCompra"],
        "precioVenta": products["precioVenta"],
        "cantidadEnStock": products["cantidadEnStock"],
        "unidadDeMedida": products["unidadDeMedida"],
        "proveedorId": products["proveedorId"],
        "fechaDeCaducidad": products["fechaDeCaducidad"],
        "fechaDeCreacion": products["fechaDeCreacion"],
        # "state": promotions["state"],
        "local": products["local"],
    }

def seller_helper(sellers) -> dict:
    return {
        "id": str(sellers["_id"]),
        "nombreVendedor": sellers["nombreVendedor"],
        "aliasVendedor": sellers.get("aliasVendedor", ""),
        "local": sellers["local"],
    }
    

def provider_helper(providers) -> dict:
    
    fecha_creacion = providers.get("fechaCreacion")
    if isinstance(fecha_creacion, datetime):
        fecha_creacion = fecha_creacion.astimezone(ZoneInfo("America/Lima")).isoformat()
        
    fecha_ultimo_pago = providers.get("fechaUltimoPago")
    if isinstance(fecha_ultimo_pago, datetime):
        fecha_ultimo_pago = fecha_ultimo_pago.astimezone(ZoneInfo("America/Lima")).isoformat()
    
    return {
        "id": str(providers["_id"]),
        "nombreProvider": providers["nombreProvider"],
        "numeroProvider": providers.get("numeroProvider", ""),
        "deudaInicial": providers["deudaInicial"],
        "deudaActual": providers["deudaActual"],
        "estadoProvider": providers["estadoProvider"],
        "local": providers["local"],
        # "fechaCreacion": providers.get("fechaCreacion"),
        "fechaCreacion": fecha_creacion,
        "fechaUltimoPago": fecha_ultimo_pago,
        "pagos": providers.get("pagos", [])
    }
    
def sale_helper(sales) -> dict:
    precio_total = sales.get("precioTotal", 0.0)
    precio_total_original = sales.get("precioTotalOriginal", precio_total)
    
    fecha_venta = sales.get("fechaVenta")
    if isinstance(fecha_venta, datetime):

        fecha_venta = fecha_venta.astimezone(ZoneInfo("America/Lima")).isoformat()
    else:
        fecha_venta = str(fecha_venta)
        
    return {
        "id": str(sales["_id"]),
        "nombreVendedor": sales["nombreVendedor"] if sales.get("nombreVendedor") not in [None, ""] else "Desconocido",
        "nombreCliente": sales["nombreCliente"] ,
        "direccionCliente": sales["direccionCliente"] if sales.get("direccionCliente") not in [None, ""] else "Sin direccion",
        "fechaVenta": fecha_venta,
        # "fechaVenta": sales["fechaVenta"],
        "productos": sales["productos"],
        "precioTotal": float(precio_total) if precio_total is not None else 0.0,
        "precioTotalOriginal": float(precio_total_original) if precio_total_original is not None else 0.0,
        # "precioTotal": float(sales["precioTotal"]),
        # "precioTotalOriginal": float(sales.get("precioTotalOriginal", sales["precioTotal"])),
        "estado": sales["estado"],
        "local": sales["local"],
        "paymentMethod": sales.get("paymentMethod", "Efectivo"),
    }
    
    


# Serialización de Gastos de almacen.
_EXPENSE_TIMEZONE = ZoneInfo("America/Lima")


def expense_helper(expense: dict) -> dict:
    from datetime import timezone
    from copy import deepcopy
    from bson import ObjectId
    from bson.decimal128 import Decimal128

    result = deepcopy(expense)
    result["id"] = str(result.pop("_id"))
    for key, value in result.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, Decimal128):
            result[key] = float(value.to_decimal())
        elif isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.astimezone(_EXPENSE_TIMEZONE).isoformat()
    return result

