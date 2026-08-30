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
    from app.utils.cash_helpers import serialize
    result = {key: value for key, value in sales.items() if key not in ("operaciones", "operacionCreacion")}
    result["precioTotalOriginal"] = sales.get("precioTotalOriginal", sales.get("precioTotal", 0))
    result["nombreVendedor"] = sales.get("nombreVendedor") or "Desconocido"
    result["direccionCliente"] = sales.get("direccionCliente") or "Sin direccion"
    result["paymentMethod"] = sales.get("paymentMethod") or "Sin registrar"
    return serialize(result)


# Serialización de Gastos de almacen.
_EXPENSE_TIMEZONE = ZoneInfo("America/Lima")


def expense_helper(expense: dict) -> dict:
    from app.utils.cash_helpers import serialize
    return serialize({key: value for key, value in expense.items() if key not in ("operaciones", "operacionCreacion")})
