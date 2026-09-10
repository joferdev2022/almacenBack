from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import HTTPException

from app.db.mongo import products_liquorDb, sales_liquorDb
from app.utils.helpers_liquor import sale_helper


LIMA = ZoneInfo("America/Lima")
UTC = ZoneInfo("UTC")


def _object_id(value: str, label: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail=f"El ID de {label} no es válido.")
    return ObjectId(value)


def _money(value, label: str):
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{label} no es válido.") from exc
    if amount < 0:
        raise HTTPException(status_code=422, detail=f"{label} no puede ser negativo.")
    return amount


def _parse_datetime(value, label: str):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{label} no es válida.") from exc
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=LIMA)
    return value.astimezone(UTC)


def _parse_due_date(value):
    if isinstance(value, datetime):
        due = value
    else:
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value[:10])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="La fecha de vencimiento no es válida.") from exc
        if not isinstance(value, date):
            raise HTTPException(status_code=422, detail="La fecha de vencimiento es obligatoria.")
        due = datetime.combine(value, time.max, tzinfo=LIMA)
    if due.tzinfo is None:
        due = due.replace(tzinfo=LIMA)
    return due.astimezone(UTC)


async def retrieve_sales(page: int, xpage: int, local: int):
    if page < 1 or xpage < 1:
        raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")

    query = {"local": local}
    total = sales_liquorDb.count_documents(query)
    sales = [
        sale_helper(sale)
        for sale in sales_liquorDb.find(query)
        .sort([("fechaVenta", -1), ("_id", -1)])
        .skip((page - 1) * xpage)
        .limit(xpage)
    ]
    return {"total": total, "sales": sales, "page": page, "xpage": xpage}


def _prepare_sale(sale_data: dict):
    result = deepcopy(sale_data)
    result.pop("_id", None)
    result.pop("id", None)
    result["_id"] = ObjectId()
    result["fechaVenta"] = _parse_datetime(result.get("fechaVenta"), "La fecha de venta")
    result["created_at"] = datetime.now(timezone.utc)

    calculated_total = 0.0
    for item in result.get("productos", []):
        quantity = int(item.get("cantidad", 0))
        equivalence = int(item.get("equivalenciaUnidades") or 1)
        purchase_price = _money(item.get("precioCompraUnitario", 0), "El precio de compra")
        sale_price = _money(item.get("precioVentaUnitario", 0), "El precio de venta")
        if quantity <= 0 or equivalence <= 0 or sale_price <= 0:
            raise HTTPException(status_code=422, detail="Los productos contienen valores inválidos.")

        item["unidadesVendidas"] = quantity * equivalence
        item["subtotalCosto"] = round(quantity * equivalence * purchase_price, 2)
        item["subtotalVenta"] = round(quantity * sale_price, 2)
        calculated_total += item["subtotalVenta"]

    calculated_total = round(calculated_total, 2)
    payment = result.setdefault("pago", {})
    received_total = _money(payment.get("total", 0), "El total")
    if calculated_total <= 0 or received_total != calculated_total:
        raise HTTPException(
            status_code=422,
            detail="El total debe coincidir con los productos de la venta.",
        )

    if result.get("condicionPago") == "credito":
        customer = result.get("clienteCredito") or {}
        name = str(customer.get("nombre") or "").strip()
        if len(name) < 2:
            raise HTTPException(
                status_code=422,
                detail="El nombre del cliente es obligatorio para una venta a crédito.",
            )
        result["clienteCredito"] = {
            "nombre": name,
            "telefono": str(customer.get("telefono") or "").strip() or None,
        }
        due_date = _parse_due_date(result.get("fechaVencimiento"))
        if due_date.astimezone(LIMA).date() < result["fechaVenta"].astimezone(LIMA).date():
            raise HTTPException(
                status_code=422,
                detail="La fecha de vencimiento no puede ser anterior a la venta.",
            )
        result["fechaVencimiento"] = due_date
        result["observacionesCredito"] = (
            str(result.get("observacionesCredito") or "").strip() or None
        )
        result["estado"] = "credito"
        payment.update(
            tipo="credito",
            total=calculated_total,
            pagado=0.0,
            saldoPendiente=calculated_total,
            estadoPago="pendiente",
            pagos=[],
        )
    else:
        method = str(payment.get("tipo") or "").strip().lower()
        if method in ("", "credito"):
            raise HTTPException(status_code=422, detail="Selecciona un método de pago válido.")
        result["condicionPago"] = "contado"
        result["clienteCredito"] = None
        result["fechaVencimiento"] = None
        result["observacionesCredito"] = None
        result["estado"] = "cancelado"
        payment.update(
            total=calculated_total,
            pagado=calculated_total,
            saldoPendiente=0.0,
            estadoPago="pagado",
            pagos=[
                {
                    "id": str(ObjectId()),
                    "monto": calculated_total,
                    "fecha": result["fechaVenta"],
                    "metodo": method,
                    "referencia": None,
                    "observaciones": None,
                }
            ],
        )

    return result


def _decrease_stock(sale_data: dict):
    quantities = {}
    for item in sale_data.get("productos", []):
        product_id = _object_id(item.get("productoId", ""), "producto")
        quantities[product_id] = quantities.get(product_id, 0) + item["unidadesVendidas"]

    applied = []
    for product_id, units in quantities.items():
        update = products_liquorDb.update_one(
            {
                "_id": product_id,
                "local": sale_data["local"],
                "cantidadEnStock": {"$gte": units},
            },
            {"$inc": {"cantidadEnStock": -units}},
        )
        if not update.matched_count:
            for previous_id, previous_units in applied:
                products_liquorDb.update_one(
                    {"_id": previous_id},
                    {"$inc": {"cantidadEnStock": previous_units}},
                )
            raise HTTPException(
                status_code=409,
                detail="Un producto no pertenece al local o no tiene stock suficiente.",
            )
        applied.append((product_id, units))
    return applied


async def add_sale(sale_data: dict) -> dict:
    sale = _prepare_sale(sale_data)
    applied_stock = _decrease_stock(sale)
    try:
        inserted = sales_liquorDb.insert_one(sale)
    except Exception:
        for product_id, units in applied_stock:
            products_liquorDb.update_one(
                {"_id": product_id},
                {"$inc": {"cantidadEnStock": units}},
            )
        raise
    return sale_helper(sales_liquorDb.find_one({"_id": inserted.inserted_id}))


async def delete_sale_by_id(sale_id: str):
    object_id = _object_id(sale_id, "venta")
    sale = sales_liquorDb.find_one({"_id": object_id})
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    is_credit = sale.get("condicionPago") == "credito" or (
        sale.get("estado") == "credito" and "condicionPago" not in sale
    )
    if is_credit and sale.get("pago", {}).get("pagos"):
        raise HTTPException(
            status_code=409,
            detail=(
                "No se puede eliminar una venta a crédito que ya tiene abonos. "
                "Debe conservarse su historial de pagos."
            ),
        )

    quantities = {}
    for item in sale.get("productos", []):
        product_id = _object_id(item.get("productoId", ""), "producto")
        units = item.get("unidadesVendidas", item.get("cantidad", 0))
        quantities[product_id] = quantities.get(product_id, 0) + units

    for product_id, units in quantities.items():
        products_liquorDb.update_one(
            {"_id": product_id},
            {"$inc": {"cantidadEnStock": units}},
        )
    sales_liquorDb.delete_one({"_id": object_id})
    return sale_helper(sale)


async def get_daily_Sales_summary(local: int):
    now = datetime.now(LIMA)
    start_local = datetime(now.year, now.month, now.day, tzinfo=LIMA)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    total_sales = 0.0
    net_profit = 0.0
    sale_count = 0
    credit_payments = 0.0

    for sale in sales_liquorDb.find({"local": local}):
        sale_date = sale.get("fechaVenta")
        if isinstance(sale_date, datetime):
            comparable_sale_date = (
                sale_date if sale_date.tzinfo else sale_date.replace(tzinfo=timezone.utc)
            )
            if start_utc <= comparable_sale_date < end_utc:
                sale_count += 1
                net_profit += sum(
                    item.get("subtotalVenta", 0) - item.get("subtotalCosto", 0)
                    for item in sale.get("productos", [])
                )

        is_credit = sale.get("condicionPago") == "credito" or (
            sale.get("estado") == "credito" and "condicionPago" not in sale
        )
        for payment in sale.get("pago", {}).get("pagos", []):
            payment_date = payment.get("fecha")
            if not isinstance(payment_date, datetime):
                continue
            comparable_payment_date = (
                payment_date
                if payment_date.tzinfo
                else payment_date.replace(tzinfo=timezone.utc)
            )
            if start_utc <= comparable_payment_date < end_utc:
                if is_credit:
                    credit_payments += payment.get("monto", 0)
                else:
                    total_sales += payment.get("monto", 0)

    return {
        "ganancia_neta": round(net_profit, 2),
        "ventas_totales": round(total_sales, 2),
        "numero_ventas": sale_count,
        "pagos_parciales_hoy": round(credit_payments, 2),
    }
