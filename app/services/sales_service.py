"""Ventas de almacen: operación, stock y Caja se confirman juntos."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from bson import ObjectId
from fastapi import HTTPException

from app.db.mongo import salesDb, productsDb
from app.models.payment_model import is_cash
from app.models.sales_model import saleModel, SalePaymentModel
from app.services import cash_service as cash
from app.services.cash_effects import capture_payment, revise_payment
from app.utils.cash_helpers import LIMA, ZERO, date_filter, money, object_id
from app.utils.helpers import sale_helper
from app.utils.operation_helpers import ensure_active, operation_hash, stamp, was_applied


def _sale(sale_id, user, session=None):
    sale = salesDb.find_one({"_id": object_id(sale_id, "venta"), "local": user["local"]}, session=session)
    if sale is None:
        raise HTTPException(404, "Venta no encontrada.")
    return sale


def get_sale_by_id(sale_id, user):
    return sale_helper(_sale(sale_id, user))


def retrieve_sales(page, xpage, local, credits=False):
    query = {"local": local, "anulado": {"$ne": True}}
    if credits:
        query["estado"] = "credito"
    count = salesDb.count_documents(query)
    rows = salesDb.find(query).sort([("fechaVenta", -1), ("_id", -1)]).skip((page - 1) * xpage).limit(xpage)
    return {"sales": [sale_helper(row) for row in rows], "total": count, "page": page, "xpage": xpage}


def get_sales_with_credit_state(page, xpage, local):
    return retrieve_sales(page, xpage, local, credits=True)


def _values(data: saleModel):
    result = data.model_dump(exclude={"id", "fechaVenta", "precioTotalOriginal", "local"})
    total = sum((item.precioUnitario * item.cantidad for item in data.productos), ZERO)
    if total <= ZERO or total != money(data.precioTotal):
        raise HTTPException(422, "El total debe coincidir con los productos y ser mayor a cero.")
    for item in result["productos"]:
        object_id(item["productoId"], "producto")
        item["precioUnitario"] = float(item["precioUnitario"])
    result["precioTotal"] = float(total)
    result["precioTotalOriginal"] = float(total)
    result["estado"] = "credito" if result["estado"] == "pendiente" else result["estado"]
    return result


def _stock_change(old_items, new_items, local, session):
    quantities = {}
    for sign, rows in ((1, old_items), (-1, new_items)):
        for item in rows:
            product_id = object_id(item["productoId"], "producto")
            quantities[product_id] = quantities.get(product_id, 0) + sign * item["cantidad"]
    for product_id, delta in quantities.items():
        if not delta:
            continue
        query = {"_id": product_id, "local": local}
        if delta < 0:
            query["cantidadEnStock"] = {"$gte": -delta}
        result = productsDb.update_one(query, {"$inc": {"cantidadEnStock": delta}}, session=session)
        if not result.matched_count and delta < 0:
            raise HTTPException(409, "Un producto no pertenece a tu local o no tiene stock suficiente.")


def _write(sale, session):
    salesDb.update_one({"_id": sale["_id"], "local": sale["local"]},
        {"$set": {key: value for key, value in sale.items() if key != "_id"}}, session=session)
    return sale_helper(sale)


def _collect(sale, amount, method, payment_date, key, user, session, kind="ABONO"):
    receipt = {"id": key, "monto": float(amount), "metodoPago": method.upper(),
               "fecha": datetime.now(timezone.utc), "fechaPago": date_filter(payment_date, None)["$gte"],
               "tipo": kind, "usuarioId": user["_id"], "anulado": False}
    receipt["pagoCaja"] = capture_payment(user, session, "VENTA", sale["_id"],
        f"VENTA:{sale['_id']}:{key}", amount if is_cash(method) else ZERO,
        ("Venta" if kind == "VENTA" else "Abono de venta") + " " + str(sale["_id"])[-8:])
    sale.setdefault("pagos", []).append(receipt)
    sale["controlCobros"] = True
    return receipt


def add_sale(data: saleModel, user, key):
    digest = operation_hash("CREAR", data.model_dump(mode="json"))
    values = _values(data)
    def write(session):
        existing = salesDb.find_one({"local": user["local"], "operacionCreacion": key}, session=session)
        if existing:
            was_applied(existing, key, digest)
            return sale_helper(existing)
        now = datetime.now(timezone.utc)
        sale = {**deepcopy(values), "_id": ObjectId(), "local": user["local"], "usuarioId": user["_id"],
                "fechaVenta": now, "created_at": now, "operacionCreacion": key,
                "anulado": False, "pagos": [], "controlCobros": True}
        total = money(sale["precioTotal"])
        sale["saldoPendiente"] = 0.0 if sale["estado"] == "cancelado" else float(total)
        if sale["estado"] == "cancelado":
            _collect(sale, total, sale["paymentMethod"], now.astimezone(LIMA).date(), key, user, session, "VENTA")
        _stock_change([], sale["productos"], user["local"], session)
        stamp(sale, key, digest, user, "CREAR")
        salesDb.insert_one(sale, session=session)
        return sale_helper(sale)
    return cash.transaction(write)


def update_payment_by_id(sale_id, data: SalePaymentModel, user, key):
    digest = operation_hash("COBRAR", data.model_dump(mode="json"))
    def write(session):
        sale = _sale(sale_id, user, session)
        if was_applied(sale, key, digest):
            return sale_helper(sale)
        ensure_active(sale)
        if sale["estado"] not in ("credito", "pendiente"):
            raise HTTPException(409, "Esta venta ya está pagada. Actualiza el listado.")
        balance = money(sale.get("saldoPendiente", sale["precioTotal"]))
        if data.monto > balance:
            raise HTTPException(422, "El abono no puede superar el saldo pendiente.")
        sale.setdefault("precioTotalOriginal", sale["precioTotal"])
        _collect(sale, data.monto, data.metodoPago, data.fechaPago, key, user, session)
        balance -= data.monto
        sale["saldoPendiente"] = float(balance)
        sale["precioTotal"] = float(balance) if balance else sale["precioTotalOriginal"]
        if balance == ZERO:
            sale.update(estado="cancelado", fechaCancelacion=datetime.now(timezone.utc))
        stamp(sale, key, digest, user, "COBRAR")
        return _write(sale, session)
    return cash.transaction(write)


def update_state_by_id(sale_id, new_state, reason, user, key):
    if new_state != "credito":
        raise HTTPException(422, "Para marcar una venta como pagada registra el cobro con monto, método y fecha.")
    digest = operation_hash("CORREGIR_COBRO", {"estado": new_state, "motivo": reason})
    def write(session):
        sale = _sale(sale_id, user, session)
        if was_applied(sale, key, digest):
            return sale_helper(sale)
        ensure_active(sale)
        if sale["estado"] != "cancelado":
            raise HTTPException(409, "La venta ya está pendiente de cobro.")
        changes = []
        for index, receipt in enumerate(sale.get("pagos", [])):
            if receipt.get("anulado"):
                continue
            receipt["pagoCaja"], adjustment = revise_payment(receipt.get("pagoCaja"), ZERO, user, session,
                "VENTA", sale["_id"], f"VENTA:{sale['_id']}:{key}:{index}",
                "Corrección de cobro inexistente: " + reason)
            receipt["anulado"] = True
            if adjustment:
                changes.append(adjustment)
        total = sale.get("precioTotalOriginal", sale["precioTotal"])
        sale.update(estado="credito", saldoPendiente=total, precioTotal=total, fechaCancelacion=None)
        stamp(sale, key, digest, user, "CORREGIR_COBRO", reason, changes)
        return _write(sale, session)
    return cash.transaction(write)


def update_sale_by_id(sale_id, data: saleModel, user, key):
    digest, values = operation_hash("EDITAR", data.model_dump(mode="json")), _values(data)
    def write(session):
        sale = _sale(sale_id, user, session)
        if was_applied(sale, key, digest):
            return sale_helper(sale)
        ensure_active(sale)
        if values["estado"] != sale["estado"]:
            raise HTTPException(422, "Usa las acciones de cobro o corrección para cambiar el estado.")
        receipts = [p for p in sale.get("pagos", []) if not p.get("anulado")]
        changed = any(values.get(k) != sale.get(k) for k in ("productos", "paymentMethod", "precioTotalOriginal"))
        if changed and receipts and (len(receipts) != 1 or receipts[0].get("tipo") != "VENTA"):
            raise HTTPException(409, "Esta venta tiene abonos. No se pueden reemplazar sus importes ni métodos desde Editar.")
        before = {k: sale.get(k) for k in ("precioTotalOriginal", "paymentMethod", "productos")}
        _stock_change(sale["productos"], values["productos"], user["local"], session)
        changes = []
        if changed and sale["estado"] == "cancelado" and receipts:
            receipt = receipts[0]
            target = money(values["precioTotal"]) if is_cash(values["paymentMethod"]) else ZERO
            receipt["pagoCaja"], adjustment = revise_payment(receipt.get("pagoCaja"), target, user, session,
                "VENTA", sale["_id"], f"VENTA:{sale['_id']}:{key}", "Corrección de importe o método de venta")
            receipt["monto"], receipt["metodoPago"] = values["precioTotal"], values["paymentMethod"].upper()
            if adjustment:
                changes.append(adjustment)
        if sale["estado"] == "credito" and receipts:
            values["precioTotal"] = sale["precioTotal"]
        sale.update(values)
        if sale["estado"] == "credito" and not receipts:
            sale["saldoPendiente"] = values["precioTotal"]
        changes.insert(0, {"antes": before, "despues": {k: sale.get(k) for k in before}})
        stamp(sale, key, digest, user, "EDITAR", changes=changes)
        return _write(sale, session)
    return cash.transaction(write)


def delete_sale_by_id(sale_id, user, key, reason):
    digest = operation_hash("ANULAR", reason)
    def write(session):
        sale = _sale(sale_id, user, session)
        if was_applied(sale, key, digest) or sale.get("anulado"):
            return sale_helper(sale)
        changes = []
        for index, receipt in enumerate(sale.get("pagos", [])):
            if receipt.get("anulado"):
                continue
            receipt["pagoCaja"], adjustment = revise_payment(receipt.get("pagoCaja"), ZERO, user, session,
                "VENTA", sale["_id"], f"VENTA:{sale['_id']}:{key}:{index}", "Anulación de venta: " + reason, annul=True)
            receipt["anulado"] = True
            if adjustment:
                changes.append(adjustment)
        _stock_change(sale["productos"], [], user["local"], session)
        sale.update(anulado=True, anulado_at=datetime.now(timezone.utc), anulado_by=user["_id"], motivoAnulacion=reason)
        stamp(sale, key, digest, user, "ANULAR", reason, changes)
        return _write(sale, session)
    return cash.transaction(write)


def _in_day(value, start, end):
    if not isinstance(value, datetime):
        return False
    return start <= (value if value.tzinfo else value.replace(tzinfo=timezone.utc)) < end


def get_daily_Sales_summary(local):
    today = datetime.now(LIMA).date()
    dates = date_filter(today, today)
    start, end = dates["$gte"], dates["$lt"]
    query = {"local": local, "anulado": {"$ne": True}, "$or": [
        {"fechaVenta": dates}, {"fechaCancelacion": dates}, {"pagos.fecha": dates}]}
    totals, partials, profit, count = ZERO, ZERO, ZERO, 0
    for sale in salesDb.find(query):
        counted = False
        if sale.get("controlCobros"):
            for receipt in sale.get("pagos", []):
                if receipt.get("anulado") or not _in_day(receipt.get("fecha"), start, end):
                    continue
                amount = money(receipt["monto"])
                if receipt.get("tipo") == "VENTA":
                    totals += amount
                    counted = True
                else:
                    partials += amount
        else:
            # Documentos previos: conservar su convención, sin crear pagos históricos.
            if sale["estado"] == "cancelado" and any(_in_day(sale.get(k), start, end) for k in ("fechaVenta", "fechaCancelacion")):
                totals += money(sale["precioTotal"])
                counted = True
            if sale["estado"] == "credito":
                partials += sum((money(p["monto"]) for p in sale.get("pagos", [])
                    if _in_day(p.get("fecha"), start, end)), ZERO)
        if counted:
            count += 1
            profit += sum(((money(p["precioUnitario"]) - money(p.get("precioBuy", 0))) * p["cantidad"]
                          for p in sale.get("productos", [])), ZERO)
    return {"ganancia_neta": float(profit), "ventas_totales": float(totals),
            "numero_ventas": count, "pagos_parciales_hoy": float(partials)}
