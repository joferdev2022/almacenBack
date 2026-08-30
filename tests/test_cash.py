"""Caja con persistencia transaccional en memoria. Nunca conecta a MongoDB.
Estos tests prueban reglas/rollback; los índices reales se verifican por separado.
"""
import json
import sys
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import FastAPI, HTTPException
from pymongo.errors import DuplicateKeyError, OperationFailure

from memory_db import MemoryDatabase, database_patches
from app.services import cash_service as service
from app.routes import cash_route, sales_route, expenses_route
from app.services import sales_service as sales, expenses_service as expenses
from app.models.sales_model import saleModel, SalePaymentModel
from app.models.expense_model import ExpenseModel, ExpensePaymentModel
from app.models.cash_model import CashClosing, CashManualMovement, CashOpening


class CashTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.registers, self.journals, self.movements = self.db.cashRegistersDb, self.db.cashJournalsDb, self.db.cashMovementsDb
        self.client = self.db.client
        for item in database_patches(self.db):
            item.start()
            self.addCleanup(item.stop)
        service.ensure_indexes()
        self.user = {"_id": ObjectId(), "username": "caja-test", "local": 1, "permissions": 1}
        self.foreign = {"_id": ObjectId(), "username": "otro-local", "local": 2, "permissions": 1}
        self.api = FastAPI()
        self.api.include_router(cash_route.router, prefix="/api")
        self.api.include_router(sales_route.router, prefix="/api")
        self.api.include_router(expenses_route.router, prefix="/api")
        self.product = {"_id": ObjectId(), "local": 1, "cantidadEnStock": 100}
        self.db.productsDb.insert_one(self.product)
        self.api.dependency_overrides[cash_route.get_current_user] = lambda: self.user

    def opening(self, amount="500", **overrides):
        return {"operacionId": str(uuid4()), "montoApertura": amount, **overrides}

    def opened(self, amount="500"):
        return service.open_journal(CashOpening(**self.opening(amount)), self.user)

    def movement(self, journal, amount, direction="INGRESO", **overrides):
        return service.manual_movement(journal["id"], CashManualMovement(
            operacionId=str(uuid4()), monto=amount, motivo="Fondo de prueba", **overrides), self.user, direction)

    def closing(self, journal, **overrides):
        return CashClosing(operacionId=str(uuid4()), montoContado="295", fondoSiguiente="200",
                           version=service.get_journal(journal["id"], self.user)["version"], **overrides)

    def assert_http(self, status, operation):
        with self.assertRaises(HTTPException) as result:
            operation()
        self.assertEqual(result.exception.status_code, status)

    async def request(self, method, path, data=None, key=None, **params):
        body = json.dumps(data).encode() if data is not None else b""
        messages = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                 "root_path": "", "query_string": urlencode(params).encode(),
                 "headers": [(b"content-type", b"application/json"), (b"idempotency-key", (key or str(uuid4())).encode())],
                 "client": ("127.0.0.1", 12345), "server": ("test", 80)}
        await self.api(scope, receive, send)
        status = next(item["status"] for item in messages if item["type"] == "http.response.start")
        payload = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
        return status, json.loads(payload)

    def test_opening_and_activation_without_backfill(self):
        self.assertIsNone(service.current_cash(self.user)["caja"])
        self.assertIsNone(service.transaction(lambda session: service.require_cash_for_operation(self.user, session)))
        self.assertIsNone(self.registers.documents[0]["inicioControl"])
        journal = self.opened()
        self.assertEqual(journal["resumen"]["saldoEsperado"], 500)
        self.assertEqual(journal["usuarioAperturaId"], str(self.user["_id"]))
        self.assertEqual(journal["local"], 1)
        self.assertIsNotNone(self.registers.documents[0]["inicioControl"])
        self.assertEqual(self.movements.documents, [])

    def test_manual_income_and_withdrawal(self):
        journal = self.opened()
        self.movement(journal, "100")
        self.movement(journal, "150", "EGRESO")
        summary = service.get_journal(journal["id"], self.user)["resumen"]
        self.assertEqual(summary["saldoEsperado"], 450)
        self.assertEqual(summary["otrosIngresos"], 100)
        self.assertEqual(summary["retiros"], 150)

    def test_close_difference_withdrawal_and_next_fund(self):
        journal = self.opened("300")
        request = self.closing(journal)
        closed = service.close_journal(journal["id"], request, self.user)
        self.assertEqual(closed["saldoEsperado"], 300)
        self.assertEqual(closed["diferencia"], -5)
        self.assertEqual(closed["retiroCierre"], 95)
        self.assertEqual(closed["resumen"]["saldoEsperado"], 300)
        self.assertEqual(closed["resumen"]["saldoTrasRetiro"], 205)
        self.assertEqual(closed["fondoSiguiente"], 200)
        self.assertEqual(service.current_cash(self.user)["fondoSugerido"], 200)
        next_journal = self.opened("190")
        self.assertEqual(next_journal["fondoEsperado"], 200)
        self.assertEqual(next_journal["diferenciaApertura"], -10)
        self.assertEqual(service.get_journal(journal["id"], self.user)["fondoSiguiente"], 200)

    def test_cash_required_only_after_activation(self):
        journal = self.opened()
        service.close_journal(journal["id"], self.closing(journal), self.user)
        self.assert_http(409, lambda: service.transaction(lambda s: service.require_cash_for_operation(self.user, s)))
        self.assertIsNone(service.transaction(lambda s: service.require_cash_for_operation(self.foreign, s)))

    def test_open_is_idempotent_but_conflicting_payload_is_rejected(self):
        request = self.opening()
        first = service.open_journal(CashOpening(**request), self.user)
        second = service.open_journal(CashOpening(**request), self.user)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.journals.documents), 1)
        self.assert_http(409, lambda: service.open_journal(CashOpening(**{**request, "montoApertura": "600"}), self.user))

    def test_manual_retry_does_not_duplicate_even_after_close(self):
        journal = self.opened()
        request = CashManualMovement(operacionId=uuid4(), monto="100", motivo="Fondo adicional")
        first = service.manual_movement(journal["id"], request, self.user, "INGRESO")
        service.close_journal(journal["id"], self.closing(journal), self.user)
        again = service.manual_movement(journal["id"], request, self.user, "INGRESO")
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(len([m for m in self.movements.documents if m["tipo"] == "INGRESO_MANUAL"]), 1)
        self.assert_http(409, lambda: service.manual_movement(journal["id"], request, self.user, "EGRESO"))

    def test_close_retry_does_not_duplicate_withdrawal(self):
        journal = self.opened()
        request = self.closing(journal)
        first = service.close_journal(journal["id"], request, self.user)
        second = service.close_journal(journal["id"], request, self.user)
        self.assertEqual(first, second)
        self.assertEqual(len(self.movements.documents), 1)
        self.assert_http(409, lambda: service.close_journal(journal["id"], self.closing(journal), self.user))

    def test_closed_journal_cannot_receive_new_movements(self):
        journal = self.opened()
        service.close_journal(journal["id"], self.closing(journal), self.user)
        before = deepcopy(self.movements.documents)
        self.assert_http(409, lambda: self.movement(journal, "1"))
        self.assertEqual(self.movements.documents, before)

    def test_stale_close_cannot_ignore_a_new_movement(self):
        journal = self.opened()
        request = self.closing(journal)
        self.movement(journal, "10")
        self.assert_http(409, lambda: service.close_journal(journal["id"], request, self.user))
        self.assertEqual(service.get_journal(journal["id"], self.user)["estado"], "ABIERTA")

    def test_failed_movement_rolls_back_journal_version(self):
        journal = self.opened()
        before = service.get_journal(journal["id"], self.user)
        with patch.object(self.movements, "insert_one", side_effect=RuntimeError("Simular fallo")):
            with self.assertRaises(RuntimeError):
                self.movement(journal, "10")
        self.assertEqual(service.get_journal(journal["id"], self.user), before)
        self.assertEqual(self.movements.documents, [])

    def test_failed_close_rolls_back_withdrawal_and_state(self):
        journal = self.opened()
        with patch.object(self.journals, "update_one", side_effect=RuntimeError("Simular fallo")):
            with self.assertRaises(RuntimeError):
                service.close_journal(journal["id"], self.closing(journal), self.user)
        self.assertEqual(service.get_journal(journal["id"], self.user)["estado"], "ABIERTA")
        self.assertEqual(self.movements.documents, [])

    def test_parallel_openings_allow_only_one_journal(self):
        def open_one(_):
            try:
                return self.opened()["estado"]
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(open_one, [1, 2]))
        self.assertCountEqual(outcomes, ["ABIERTA", 409])
        self.assertEqual(len(self.journals.documents), 1)

    def test_parallel_retry_records_one_income(self):
        journal = self.opened()
        request = CashManualMovement(operacionId=uuid4(), monto="10", motivo="Ingreso prueba")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: service.manual_movement(journal["id"], request, self.user, "INGRESO"), [1, 2]))
        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(service.get_journal(journal["id"], self.user)["resumen"]["saldoEsperado"], 510)

    def test_no_cross_local_access(self):
        journal = self.opened()
        self.assertIsNone(service.current_cash(self.foreign)["jornada"])
        self.assert_http(404, lambda: service.get_journal(journal["id"], self.foreign))
        self.assert_http(404, lambda: service.movements(journal["id"], self.foreign))
        self.assert_http(404, lambda: service.close_journal(journal["id"], self.closing(journal), self.foreign))
        self.assertEqual(service.history(self.foreign)["total"], 0)

    def test_exact_cents(self):
        journal = self.opened("0.10")
        for _ in range(10):
            self.movement(journal, "0.10")
        self.assertEqual(service.get_journal(journal["id"], self.user)["resumen"]["saldoEsperado"], 1.1)
        self.assertTrue(all(isinstance(row["monto"], Decimal128) for row in self.movements.documents))

    def test_filter_and_pagination(self):
        journal = self.opened()
        self.movement(journal, "10")
        self.movement(journal, "20", "EGRESO")
        page = service.movements(journal["id"], self.user, xpage=1)
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(service.movements(journal["id"], self.user, naturaleza="EGRESO")["total"], 1)
        self.assertEqual(service.movements(journal["id"], self.user, tipo="INGRESO_MANUAL")["total"], 1)
        self.assertEqual(service.movements(journal["id"], self.user, fecha_hasta=date(2000, 1, 1))["total"], 0)
        self.assert_http(422, lambda: service.history(self.user, fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 1, 1)))

    def test_transactions_are_required(self):
        with patch.object(self.client, "start_session", side_effect=OperationFailure("unsupported", code=20)):
            self.assert_http(503, lambda: self.opened())

    async def test_api_validation_and_permission(self):
        for amount in ("-1", "0.001", "NaN"):
            status, _ = await self.request("POST", "/api/cash/open", self.opening(amount))
            self.assertEqual(status, 422)
        status, response = await self.request("POST", "/api/cash/open", self.opening("0"))
        self.assertEqual(status, 201, response)
        journal_id = response["data"]["id"]
        for amount in ("0", "-1", "1.001"):
            status, _ = await self.request("POST", f"/api/cash/{journal_id}/income",
                {"operacionId": str(uuid4()), "monto": amount, "motivo": "Ingreso"})
            self.assertEqual(status, 422)
        status, _ = await self.request("POST", f"/api/cash/{journal_id}/close",
            {"operacionId": str(uuid4()), "montoContado": "10", "fondoSiguiente": "11", "version": 0})
        self.assertEqual(status, 422)
        status, _ = await self.request("GET", "/api/cash/history", page=0)
        self.assertEqual(status, 422)
        status, _ = await self.request("GET", "/api/cash/invalid-id")
        self.assertEqual(status, 400)
        self.user["permissions"] = 0
        status, _ = await self.request("POST", f"/api/cash/{journal_id}/income",
            {"operacionId": str(uuid4()), "monto": "10", "motivo": "Ingreso"})
        self.assertEqual(status, 403)
        status, _ = await self.request("GET", "/api/cash/current")
        self.assertEqual(status, 200)

    async def test_client_cannot_set_user_or_local(self):
        status, _ = await self.request("POST", "/api/cash/open", self.opening(local=2, usuarioId=str(self.foreign["_id"])))
        self.assertEqual(status, 422)
        self.assertEqual(self.journals.documents, [])

    def sale_payload(self, amount=100, state="cancelado", method="efectivo", **overrides):
        return {"nombreVendedor": "Vendedor", "nombreCliente": "Cliente prueba", "direccionCliente": "",
                "precioTotal": amount, "estado": state, "paymentMethod": method, "local": 999,
                "productos": [{"productoId": str(self.product["_id"]), "cantidad": 1,
                    "precioUnitario": amount, "precioBuy": 5, "productName": "Producto"}], **overrides}

    def create_sale(self, amount=100, state="cancelado", method="efectivo", key=None):
        return sales.add_sale(saleModel(**self.sale_payload(amount, state, method)), self.user, key or str(uuid4()))

    def expense_payload(self, amount=50, state="PAGADO", method="EFECTIVO"):
        return {"fecha": "2026-08-28", "categoria": "Servicios", "descripcion": "Pago de prueba",
                "monto": amount, "estado": state, "metodoPago": method}

    def create_expense(self, amount=50, state="PAGADO", method="EFECTIVO", key=None):
        return expenses.add_expense(ExpenseModel(**self.expense_payload(amount, state, method)), self.user, key or str(uuid4()))

    def balance(self, journal):
        return service.get_journal(journal["id"], self.user)["resumen"]["saldoEsperado"]

    def test_complete_requested_cash_flow(self):
        journal = self.opened()
        key = str(uuid4())
        sale = self.create_sale(key=key)
        self.assertEqual(self.balance(journal), 600)
        self.create_sale(200, method="yape")
        self.assertEqual(self.balance(journal), 600)
        self.create_expense(50)
        self.assertEqual(self.balance(journal), 550)
        self.create_expense(100, method="TRANSFERENCIA")
        self.assertEqual(self.balance(journal), 550)
        pending = self.create_expense(200, "PENDIENTE", None)
        self.assertEqual(self.balance(journal), 550)
        expenses.pay_expense_by_id(pending["id"], ExpensePaymentModel(metodoPago="EFECTIVO", fechaPago="2026-08-28"), self.user, str(uuid4()))
        self.assertEqual(self.balance(journal), 350)
        self.movement(journal, "100")
        self.assertEqual(self.balance(journal), 450)
        self.movement(journal, "150", "EGRESO")
        self.assertEqual(self.balance(journal), 300)
        self.assertEqual(self.create_sale(key=key)["id"], sale["id"])
        self.assertEqual(self.balance(journal), 300)
        closed = service.close_journal(journal["id"], self.closing(journal), self.user)
        self.assertEqual(closed["diferencia"], -5)
        self.assertEqual(closed["fondoSiguiente"], 200)
        self.assertEqual(service.current_cash(self.user)["fondoSugerido"], 200)

    def test_all_non_cash_methods_leave_physical_balance_unchanged(self):
        journal = self.opened()
        for method in ("YAPE", "PLIN", "TRANSFERENCIA", "OTRO"):
            self.create_sale(method=method)
            self.create_expense(method=method)
        self.assertEqual(self.balance(journal), 500)
        self.assertEqual(self.movements.documents, [])

    def test_missing_open_cash_rolls_back_sale_expense_and_payment(self):
        journal = self.opened()
        credit = self.create_sale(state="credito", method=None)
        pending = self.create_expense(state="PENDIENTE", method=None)
        service.close_journal(journal["id"], self.closing(journal), self.user)
        stock = self.db.productsDb.documents[0]["cantidadEnStock"]
        self.assert_http(409, lambda: self.create_sale())
        self.assert_http(409, lambda: self.create_expense())
        self.assert_http(409, lambda: sales.update_payment_by_id(credit["id"],
            SalePaymentModel(monto=10, metodoPago="EFECTIVO", fechaPago="2026-08-28"), self.user, str(uuid4())))
        self.assert_http(409, lambda: expenses.pay_expense_by_id(pending["id"],
            ExpensePaymentModel(metodoPago="EFECTIVO", fechaPago="2026-08-28"), self.user, str(uuid4())))
        self.assertEqual(len(self.db.salesDb.documents), 1)
        self.assertEqual(len(self.db.expensesDb.documents), 1)
        self.assertEqual(self.db.productsDb.documents[0]["cantidadEnStock"], stock)
        self.assertEqual(sales.get_sale_by_id(credit["id"], self.user)["saldoPendiente"], 100)
        self.create_sale(method="yape")
        self.create_expense(method="TRANSFERENCIA")

    def test_expense_correction_and_annulment_keep_trace(self):
        journal = self.opened()
        expense = self.create_expense()
        expenses.update_expense_by_id(expense["id"], ExpenseModel(**self.expense_payload(80)), self.user, str(uuid4()))
        self.assertEqual(self.balance(journal), 420)
        expenses.update_expense_by_id(expense["id"], ExpenseModel(**self.expense_payload(80, method="TRANSFERENCIA")), self.user, str(uuid4()))
        self.assertEqual(self.balance(journal), 500)
        expenses.update_expense_by_id(expense["id"], ExpenseModel(**self.expense_payload(80)), self.user, str(uuid4()))
        key = str(uuid4())
        result = expenses.delete_expense_by_id(expense["id"], self.user, key, "Reintegro del gasto")
        self.assertTrue(result["anulado"])
        self.assertEqual(self.balance(journal), 500)
        expenses.delete_expense_by_id(expense["id"], self.user, key, "Reintegro del gasto")
        self.assertEqual(self.balance(journal), 500)
        self.assertEqual(len(self.db.expensesDb.documents), 1)
        self.assertEqual(expenses.retrieve_expenses(self.user, 1, 10)["total"], 0)

    def test_sale_edit_and_annulment_restore_stock_once(self):
        journal = self.opened()
        sale = self.create_sale()
        sales.update_sale_by_id(sale["id"], saleModel(**self.sale_payload(120)), self.user, str(uuid4()))
        self.assertEqual(self.balance(journal), 620)
        self.assertEqual(self.db.productsDb.documents[0]["cantidadEnStock"], 99)
        key = str(uuid4())
        result = sales.delete_sale_by_id(sale["id"], self.user, key, "Devolución de venta")
        sales.delete_sale_by_id(sale["id"], self.user, key, "Devolución de venta")
        self.assertTrue(result["anulado"])
        self.assertEqual(self.balance(journal), 500)
        self.assertEqual(self.db.productsDb.documents[0]["cantidadEnStock"], 100)
        self.assertEqual(sales.retrieve_sales(1, 10, 1)["total"], 0)
        self.assertEqual(len(self.db.salesDb.documents), 1)

    def test_closed_uncollected_sale_correction_does_not_invent_current_withdrawal(self):
        first = self.opened()
        sale = self.create_sale()
        closed = service.close_journal(first["id"], CashClosing(operacionId=uuid4(), montoContado=500,
            fondoSiguiente=500, version=service.get_journal(first["id"], self.user)["version"]), self.user)
        self.assertEqual(closed["diferencia"], -100)
        current = self.opened()
        sales.update_state_by_id(sale["id"], "credito", "Nunca se cobró esta venta", self.user, str(uuid4()))
        self.assertEqual(self.balance(current), 500)
        self.assertEqual(service.get_journal(first["id"], self.user)["diferencia"], -100)
        original_movements = service.movements(first["id"], self.user)["items"]
        self.assertTrue(original_movements[0]["correccionPosterior"])
        sales.update_payment_by_id(sale["id"], SalePaymentModel(monto=100, metodoPago="EFECTIVO",
            fechaPago="2026-08-28"), self.user, str(uuid4()))
        self.assertEqual(self.balance(current), 600)

    def test_closed_source_annulment_reverts_in_current_journal(self):
        first = self.opened()
        sale = self.create_sale()
        closed = service.close_journal(first["id"], CashClosing(operacionId=uuid4(), montoContado=600,
            fondoSiguiente=500, version=service.get_journal(first["id"], self.user)["version"]), self.user)
        current = self.opened()
        sales.delete_sale_by_id(sale["id"], self.user, str(uuid4()), "Devolución actual")
        self.assertEqual(self.balance(current), 400)
        self.assertEqual(service.get_journal(first["id"], self.user)["saldoEsperado"], closed["saldoEsperado"])

    def test_credit_payments_have_independent_methods_ids_and_exact_final_balance(self):
        journal = self.opened()
        sale = self.create_sale(200, state="credito", method=None)
        self.assertEqual(self.balance(journal), 500)
        key = str(uuid4())
        payment = SalePaymentModel(monto=50, metodoPago="EFECTIVO", fechaPago="2026-08-28")
        sales.update_payment_by_id(sale["id"], payment, self.user, key)
        sales.update_payment_by_id(sale["id"], payment, self.user, key)
        self.assertEqual(self.balance(journal), 550)
        final = sales.update_payment_by_id(sale["id"], SalePaymentModel(monto=150, metodoPago="YAPE",
            fechaPago="2026-08-28"), self.user, str(uuid4()))
        self.assertEqual(final["estado"], "cancelado")
        self.assertEqual(final["saldoPendiente"], 0)
        self.assertEqual(len(final["pagos"]), 2)
        self.assertEqual(final["pagos"][1]["metodoPago"], "YAPE")
        self.assertEqual(self.balance(journal), 550)
        self.assert_http(409, lambda: sales.update_payment_by_id(sale["id"], payment, self.user, str(uuid4())))

    def test_old_pending_operations_only_affect_cash_when_paid_now(self):
        old_sale = self.create_sale(state="credito", method=None)
        old_paid = self.create_sale()
        old_expense = self.create_expense(state="PENDIENTE", method=None)
        journal = self.opened()
        self.assertEqual(self.balance(journal), 500)
        sales.update_sale_by_id(old_paid["id"], saleModel(**self.sale_payload(120)), self.user, str(uuid4()))
        self.assertEqual(self.balance(journal), 500)
        sales.update_payment_by_id(old_sale["id"], SalePaymentModel(monto=100, metodoPago="EFECTIVO",
            fechaPago="2026-08-28"), self.user, str(uuid4()))
        expenses.pay_expense_by_id(old_expense["id"], ExpensePaymentModel(metodoPago="EFECTIVO",
            fechaPago="2026-08-28"), self.user, str(uuid4()))
        self.assertEqual(self.balance(journal), 550)

    def test_parallel_sale_retry_does_not_repeat_stock_or_cash(self):
        journal = self.opened()
        key = str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.create_sale(key=key), [1, 2]))
        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(self.balance(journal), 600)
        self.assertEqual(self.db.productsDb.documents[0]["cantidadEnStock"], 99)

    def test_failure_after_cash_and_stock_changes_rolls_back_everything(self):
        journal = self.opened()
        with patch.object(self.db.salesDb, "insert_one", side_effect=RuntimeError("Fallo al guardar venta")):
            with self.assertRaises(RuntimeError):
                self.create_sale()
        self.assertEqual(self.balance(journal), 500)
        self.assertEqual(self.db.productsDb.documents[0]["cantidadEnStock"], 100)
        self.assertEqual(self.db.salesDb.documents, [])
        with patch.object(self.db.expensesDb, "insert_one", side_effect=RuntimeError("Fallo al guardar gasto")):
            with self.assertRaises(RuntimeError):
                self.create_expense()
        self.assertEqual(self.balance(journal), 500)
        self.assertEqual(self.db.expensesDb.documents, [])

    def test_product_and_source_local_are_validated_on_backend(self):
        journal = self.opened()
        sale = self.create_sale()
        self.assertEqual(sale["local"], 1)
        self.assertEqual(sale["usuarioId"], str(self.user["_id"]))
        self.assert_http(404, lambda: sales.delete_sale_by_id(sale["id"], self.foreign, str(uuid4()), "Otro local"))
        foreign_product = {"_id": ObjectId(), "local": 2, "cantidadEnStock": 100}
        self.db.productsDb.insert_one(foreign_product)
        payload = self.sale_payload()
        payload["productos"][0]["productoId"] = str(foreign_product["_id"])
        self.assert_http(409, lambda: sales.add_sale(saleModel(**payload), self.user, str(uuid4())))
        self.assertEqual(self.balance(journal), 600)

    async def test_sales_api_and_idempotency_header(self):
        self.opened()
        key = str(uuid4())
        first_status, first = await self.request("POST", "/api/sales", self.sale_payload(), key=key)
        second_status, second = await self.request("POST", "/api/sales", self.sale_payload(), key=key)
        self.assertEqual(first_status, 200, first)
        self.assertEqual(second_status, 200, second)
        self.assertEqual(first["data"]["id"], second["data"]["id"])
        status, _ = await self.request("POST", "/api/sales", self.sale_payload(120), key=key)
        self.assertEqual(status, 409)
        self.user["permissions"] = 0
        status, _ = await self.request("POST", "/api/sales", self.sale_payload())
        self.assertEqual(status, 403)

    async def test_annulled_sales_are_excluded_from_existing_reports(self):
        from app.services import seller_service, dashboard_service
        from app.utils.cash_helpers import LIMA
        from datetime import datetime
        self.opened()
        self.create_sale(100)
        annulled = self.create_sale(200)
        sales.delete_sale_by_id(annulled["id"], self.user, str(uuid4()), "Anulación de prueba")
        today = datetime.now(LIMA)
        with patch.object(seller_service, "salesDb", self.db.salesDb):
            report = await seller_service.get_seller_monthly_stats("Vendedor", 1, today.year, today.month)
        self.assertEqual(report["totalVentas"], 1)
        self.assertEqual(report["montoTotal"], 100)
        with patch.object(dashboard_service, "salesDb", self.db.salesDb):
            self.assertEqual(await dashboard_service.get_monthly_net_profit({}, 1), 95)
        self.assertEqual(sales.get_daily_Sales_summary(1)["ventas_totales"], 100)

    def test_closed_expense_correction_keeps_previous_count_and_current_cash(self):
        journal = self.opened()
        expense = self.create_expense()
        service.close_journal(journal["id"], self.closing(journal), self.user)
        current = self.opened("200")
        expenses.update_expense_by_id(expense["id"], ExpenseModel(**self.expense_payload(80)), self.user, str(uuid4()))
        self.assertEqual(self.balance(current), 200)
        self.assertEqual(self.balance(journal), 450)
        detail = expenses.retrieve_expense_by_id(expense["id"], self.user)
        self.assertTrue(detail["auditoria"][-1]["cambios"][-1]["sinMovimiento"])

    def test_seller_is_optional_and_card_is_disabled_for_warehouse_sales(self):
        from pydantic import ValidationError
        payload = self.sale_payload()
        payload["nombreVendedor"] = ""
        model = saleModel(**payload)
        self.assertEqual(model.nombreVendedor, "")
        self.opened()
        saved = sales.add_sale(model, self.user, str(uuid4()))
        self.assertEqual(saved["nombreVendedor"], "Desconocido")
        payload["paymentMethod"] = "TARJETA"
        with self.assertRaises(ValidationError):
            saleModel(**payload)
        with self.assertRaises(ValidationError):
            SalePaymentModel(monto=10, metodoPago="TARJETA", fechaPago="2026-08-29")
