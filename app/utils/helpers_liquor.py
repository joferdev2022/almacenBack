from datetime import datetime
from zoneinfo import ZoneInfo
from copy import deepcopy

def product_helper(product) -> dict:
    return {
        "id": str(product["_id"]),
        "nombre": product.get("nombre"),
        "descripcion": product.get("descripcion"),
        "categoria": product.get("categoria"),
        "marca": product.get("marca"),
        "contenido": product.get("contenido"),
        "unidadContenido": product.get("unidadContenido"),
        "presentacion": product.get("presentacion"),
        "barcode": product.get("barcode"),
        "precioCompra": product.get("precioCompra"),
        "cantidadEnStock": product.get("cantidadEnStock"),
        "proveedorId": product.get("proveedorId"),
        "fechaDeCaducidad": product.get("fechaDeCaducidad"),
        "fechaDeCreacion": product.get("fechaDeCreacion"),
        "local": product.get("local"),
        "sku": [
            {
                "skuId": sku.get("skuId"),
                "nombre": sku.get("nombre"),
                "equivalenciaUnidades": sku.get("equivalenciaUnidades"),
                "precioVenta": sku.get("precioVenta"),
            }
            for sku in product.get("sku", [])
        ],
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
    
def sale_helper(sale: dict) -> dict:
    sale = deepcopy(sale)

    sale["id"] = str(sale.pop("_id"))

    # Fecha de venta
    if isinstance(sale.get("fechaVenta"), datetime):
        sale["fechaVenta"] = (
            sale["fechaVenta"]
            .astimezone(ZoneInfo("America/Lima"))
            .isoformat()
        )

    # Fechas de los pagos
    for pago in sale.get("pago", {}).get("pagos", []):
        if isinstance(pago.get("fecha"), datetime):
            pago["fecha"] = (
                pago["fecha"]
                .astimezone(ZoneInfo("America/Lima"))
                .isoformat()
            )

    return sale


def expense_helper(expense: dict) -> dict:
    expense = deepcopy(expense)
    expense["id"] = str(expense.pop("_id"))

    fecha = expense.get("fecha")
    if isinstance(fecha, datetime):
        # PyMongo devuelve los datetimes sin tzinfo como UTC por defecto.
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=ZoneInfo("UTC"))
        expense["fecha"] = fecha.astimezone(ZoneInfo("America/Lima")).isoformat()

    return expense
    
    
