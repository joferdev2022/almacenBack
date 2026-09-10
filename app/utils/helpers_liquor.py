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

    # Fechas principales de la venta y del crédito.
    for field in (
        "fechaVenta",
        "fechaVencimiento",
        "fechaCancelacion",
        "created_at",
        "updated_at",
    ):
        value = sale.get(field)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo("UTC"))
            sale[field] = value.astimezone(ZoneInfo("America/Lima")).isoformat()

    # Fechas de los pagos
    for pago in sale.get("pago", {}).get("pagos", []):
        if isinstance(pago.get("fecha"), datetime):
            payment_date = pago["fecha"]
            if payment_date.tzinfo is None:
                payment_date = payment_date.replace(tzinfo=ZoneInfo("UTC"))
            pago["fecha"] = payment_date.astimezone(ZoneInfo("America/Lima")).isoformat()

    payment = sale.get("pago", {})
    total = float(payment.get("total") or 0)
    paid = float(payment.get("pagado") or 0)
    balance = float(payment.get("saldoPendiente", max(total - paid, 0)) or 0)
    payment_state = payment.get("estadoPago")
    if not payment_state:
        payment_state = "pagado" if balance <= 0 else ("parcial" if paid > 0 else "pendiente")
        payment["estadoPago"] = payment_state

    sale["estadoCobro"] = payment_state
    due_date = sale.get("fechaVencimiento")
    if balance > 0 and due_date:
        try:
            comparable_due = datetime.fromisoformat(str(due_date).replace("Z", "+00:00"))
            if comparable_due.tzinfo is None:
                comparable_due = comparable_due.replace(tzinfo=ZoneInfo("America/Lima"))
            if comparable_due < datetime.now(ZoneInfo("America/Lima")):
                sale["estadoCobro"] = "vencido"
        except (TypeError, ValueError):
            pass

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
    
    
