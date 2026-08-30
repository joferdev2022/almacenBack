"""Verificación real y aislada de Caja: python -m scripts.verify_cash_integration.
Usa exclusivamente colecciones temporales codex_cash_test_* en almacen.
No abre jornadas operativas ni modifica ventas, gastos, stock o usuarios reales.
Los índices del módulo deben existir previamente (ensure_cash_indexes).
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException

from app.db import mongo
from app.models.cash_model import CashClosing, CashManualMovement, CashOpening
from app.models.expense_model import ExpenseModel, ExpensePaymentModel
from app.models.sales_model import saleModel
from app.services import cash_service as cash, sales_service as sales, expenses_service as expenses


def verify():
    database = mongo.cashRegistersDb.database
    if database.name != "almacen":
        raise RuntimeError("Esta prueba solo admite almacen.")
    prefix = "codex_cash_test_" + uuid4().hex[:12] + "_"
    handles = {
        "cashRegistersDb": "cash_registers", "cashJournalsDb": "cash_journals",
        "cashMovementsDb": "cash_movements", "salesDb": "sales",
        "expensesDb": "expenses", "productsDb": "products", "providersDb": "providers",
    }
    names = [prefix + name for name in handles.values()]
    isolated = {}
    created = []
    try:
        for attr, original in handles.items():
            target = database.create_collection(prefix + original)
            created.append(target.name)
            isolated[attr] = target
            for index in database[original].list_indexes():
                if index["name"] == "_id_":
                    continue
                options = {key: index[key] for key in ("name", "unique", "partialFilterExpression", "sparse") if key in index}
                target.create_index(list(index["key"].items()), **options)
        with ExitStack() as stack:
            for module in (cash, sales, expenses):
                for attr, collection in isolated.items():
                    if hasattr(module, attr):
                        stack.enter_context(patch.object(module, attr, collection))
            user = {"_id": ObjectId(), "username": "verificacion-aislada", "local": 987654321, "permissions": 1}
            product = ObjectId()
            isolated["productsDb"].insert_one({"_id": product, "local": user["local"], "cantidadEnStock": 100})
            def sale(amount=100, method="EFECTIVO", key=None):
                return sales.add_sale(saleModel(nombreVendedor="Prueba", nombreCliente="Prueba",
                    precioTotal=amount, paymentMethod=method, productos=[{
                        "productoId": str(product), "cantidad": 1, "precioUnitario": amount,
                        "precioBuy": 5, "productName": "Producto aislado"}]), user, key or str(uuid4()))
            def expense(amount=50, state="PAGADO", method="EFECTIVO"):
                return expenses.add_expense(ExpenseModel(fecha=date.today(), categoria="Servicios",
                    monto=amount, estado=state, metodoPago=method), user, str(uuid4()))
            def opening(amount):
                return cash.open_journal(CashOpening(operacionId=uuid4(), montoApertura=amount), user)
            def balance(journal):
                return cash.get_journal(journal["id"], user)["resumen"]["saldoEsperado"]
            def expect_conflict(call):
                try:
                    call()
                except HTTPException as error:
                    assert error.status_code == 409
                else:
                    raise AssertionError("La operación debía rechazarse.")
            def manual(journal, amount, direction):
                return cash.manual_movement(journal["id"], CashManualMovement(
                    operacionId=uuid4(), monto=amount, motivo="Verificación aislada"), user, direction)
            journal = opening(500)
            key = str(uuid4())
            paid_sale = sale(key=key)
            assert balance(journal) == 600
            sale(200, "YAPE")
            assert balance(journal) == 600
            expense()
            assert balance(journal) == 550
            expense(100, method="TRANSFERENCIA")
            pending = expense(200, "PENDIENTE", None)
            assert balance(journal) == 550
            expenses.pay_expense_by_id(pending["id"], ExpensePaymentModel(
                metodoPago="EFECTIVO", fechaPago=date.today()), user, str(uuid4()))
            manual(journal, 100, "INGRESO")
            manual(journal, 150, "EGRESO")
            assert balance(journal) == 300
            assert sale(key=key)["id"] == paid_sale["id"]
            assert balance(journal) == 300
            close_request = CashClosing(operacionId=uuid4(), montoContado=295, fondoSiguiente=200,
                version=cash.get_journal(journal["id"], user)["version"])
            closed = cash.close_journal(journal["id"], close_request, user)
            assert (closed["saldoEsperado"], closed["diferencia"], closed["retiroCierre"]) == (300, -5, 95)
            assert cash.close_journal(journal["id"], close_request, user)["id"] == closed["id"]
            assert cash.current_cash(user)["fondoSugerido"] == 200
            expect_conflict(lambda: manual(journal, 10, "INGRESO"))
            expect_conflict(lambda: sale())
            print("OK: flujo completo, reintentos, cierre y caja obligatoria.")

            barrier = Barrier(2)
            def concurrent_open(_):
                barrier.wait()
                try:
                    return opening(200)
                except HTTPException as error:
                    assert error.status_code == 409
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                opened = list(pool.map(concurrent_open, [0, 1]))
            assert sum(item is not None for item in opened) == 1
            current = next(item for item in opened if item)
            assert current["fondoEsperado"] == 200
            key = str(uuid4())
            barrier = Barrier(2)
            def repeated_sale(_):
                barrier.wait()
                return sale(key=key)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(repeated_sale, [0, 1]))
            assert results[0]["id"] == results[1]["id"]
            assert balance(current) == 300
            assert isolated["productsDb"].find_one({"_id": product})["cantidadEnStock"] == 97
            print("OK: aperturas simultáneas y venta simultánea idempotente con índices reales.")

            before = {name: collection.count_documents({}) for name, collection in isolated.items()}
            stock_before = isolated["productsDb"].find_one({"_id": product})["cantidadEnStock"]
            with patch.object(isolated["salesDb"], "insert_one", side_effect=RuntimeError("Fallo simulado tras stock y movimiento")):
                try:
                    sale()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Faltó el fallo simulado.")
            assert before == {name: collection.count_documents({}) for name, collection in isolated.items()}
            assert balance(current) == 300
            assert isolated["productsDb"].find_one({"_id": product})["cantidadEnStock"] == stock_before
            print("OK: MongoDB revierte venta, stock y movimiento dentro de la misma transacción.")

            reversal_key = str(uuid4())
            for _ in range(2):
                annulled = sales.delete_sale_by_id(results[0]["id"], user, reversal_key, "Anulación de prueba")
            assert annulled["anulado"]
            assert balance(current) == 200
            assert isolated["productsDb"].find_one({"_id": product})["cantidadEnStock"] == 98
            expense_doc = expense(50)
            updated = expenses.update_expense_by_id(expense_doc["id"], ExpenseModel(
                fecha=date.today(), categoria="Servicios", monto=80, estado="PAGADO",
                metodoPago="EFECTIVO"), user, str(uuid4()))
            assert balance(current) == 120
            expenses.delete_expense_by_id(updated["id"], user, str(uuid4()), "Anulación de prueba")
            assert balance(current) == 200
            assert isolated["expensesDb"].find_one({"_id": ObjectId(updated["id"])})["anulado"]
            print("OK: edición de gasto, anulaciones, auditoría y devolución de stock una sola vez.")

            stale = CashClosing(operacionId=uuid4(), montoContado=200, fondoSiguiente=200,
                version=cash.get_journal(current["id"], user)["version"])
            barrier = Barrier(2)
            def closing_race():
                barrier.wait()
                try:
                    return cash.close_journal(current["id"], stale, user)
                except HTTPException as error:
                    assert error.status_code == 409
                    return None
            def movement_race():
                barrier.wait()
                try:
                    return manual(current, 10, "INGRESO")
                except HTTPException as error:
                    assert error.status_code == 409
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(closing_race)
                b = pool.submit(movement_race)
                outcomes = [a.result(), b.result()]
            assert sum(item is not None for item in outcomes) == 1
            detail = cash.get_journal(current["id"], user)
            assert (detail["estado"], detail["resumen"]["saldoEsperado"]) in (("CERRADA", 200), ("ABIERTA", 210))
            print("OK: cierre concurrente con movimiento, sin pérdida de dinero ni cierre desactualizado.")
    finally:
        for name in created:
            if database.name != "almacen" or not name.startswith(prefix) or name not in names:
                raise RuntimeError("Nombre temporal no autorizado para limpieza.")
            database.drop_collection(name)
        print("Colecciones temporales eliminadas; operaciones reales sin modificar.")


if __name__ == "__main__":
    verify()
