"""Pruebas del API real con persistencia en memoria; no conectan a MongoDB.

Ejecutar: python -m unittest discover -s tests -v
"""
import json
import re
import sys
import types
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlencode

from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import FastAPI


from uuid import uuid4
from memory_db import MemoryDatabase, database_patches
from app.routes.expenses_route import router
from app.services import expenses_service as service
from app.services.auth_service import create_access_token


app = FastAPI()
app.include_router(router, prefix="/api")


class ExpensesApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.auth, self.providers, self.expenses = self.db.authDb, self.db.providersDb, self.db.expensesDb
        self.patches = database_patches(self.db)
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.writer = {"_id": ObjectId(), "username": "expense-test", "local": 1, "permissions": 1}
        self.reader = {"_id": ObjectId(), "username": "reader-test", "local": 1, "permissions": 0}
        self.foreign = {"_id": ObjectId(), "username": "other-test", "local": 2, "permissions": 1}
        for user in (self.writer, self.reader, self.foreign):
            self.auth.insert_one(user)
        self.provider = {"_id": ObjectId(), "nombreProvider": "Internet del Perú", "local": 1}
        self.other_provider = {"_id": ObjectId(), "nombreProvider": "Otro local", "local": 2}
        self.providers.insert_one(self.provider)
        self.providers.insert_one(self.other_provider)
        self.token = self.token_for(self.writer)

    def token_for(self, user):
        return create_access_token({"sub": user["username"], "local": user["local"]},
                                   expires_delta=timedelta(minutes=5))

    def payload(self, **overrides):
        return {"fecha": "2026-08-28", "categoria": "Servicios", "descripcion": "Pago de internet",
                "monto": 50, "estado": "PAGADO", "metodoPago": "EFECTIVO", **overrides}

    async def request(self, method, path="/api/expenses", data=None, token="default", **params):
        if method == "DELETE" and data is None:
            data = {"motivo": "Anulación de prueba"}
        body = json.dumps(data).encode() if data is not None else b""
        headers = [(b"content-type", b"application/json"), (b"idempotency-key", str(uuid4()).encode())]
        effective_token = self.token if token == "default" else token
        if effective_token:
            headers.append((b"authorization", ("Bearer " + effective_token).encode()))
        messages = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                 "root_path": "", "query_string": urlencode(params).encode(), "headers": headers,
                 "client": ("127.0.0.1", 12345), "server": ("test", 80)}
        await app(scope, receive, send)
        status = next(msg["status"] for msg in messages if msg["type"] == "http.response.start")
        payload = b"".join(msg.get("body", b"") for msg in messages if msg["type"] == "http.response.body")
        return status, json.loads(payload)

    async def create(self, **overrides):
        status, body = await self.request("POST", data=self.payload(**overrides))
        self.assertEqual(status, 201, body)
        return body["data"]

    async def test_paid_cash_and_transfer(self):
        for amount, method in ((50, "EFECTIVO"), (120, "TRANSFERENCIA")):
            with self.subTest(method=method):
                expense = await self.create(monto=amount, metodoPago=method)
                self.assertEqual(expense["monto"], amount)
                self.assertEqual(expense["fechaPago"], "2026-08-28T00:00:00-05:00")
                self.assertEqual(expense["usuarioId"], str(self.writer["_id"]))
                self.assertEqual(expense["local"], 1)

    async def test_pending_without_payment(self):
        expense = await self.create(monto=200, estado="PENDIENTE", metodoPago=None)
        self.assertIsNone(expense["fechaPago"])
        self.assertIsNone(expense["metodoPago"])

    async def test_invalid_business_data_rejected(self):
        cases = [
            {"metodoPago": None}, {"monto": 0}, {"monto": -100}, {"monto": "1.001"},
            {"monto": "NaN"}, {"monto": "Infinity"}, {"estado": "ANULADO"},
            {"metodoPago": "INVALIDO"}, {"fecha": "2026-02-30"},
            {"fechaPago": "no-fecha"}, {"categoria": "No existe"},
            {"estado": "PENDIENTE", "fechaPago": "2026-08-28"},
            {"usuarioId": str(ObjectId())}, {"local": 2}, {"updated_at": "2026-08-28"},
        ]
        for invalid in cases:
            with self.subTest(invalid=invalid):
                status, _ = await self.request("POST", data=self.payload(**invalid))
                self.assertEqual(status, 422)
        self.assertEqual(len(self.expenses.documents), 0)

    async def test_pay_pending_requires_both_fields_and_is_atomic(self):
        expense = await self.create(estado="PENDIENTE", metodoPago=None)
        path = f"/api/expenses/{expense['id']}/pay"
        for data in ({}, {"metodoPago": "YAPE"}, {"fechaPago": "2026-08-29"}):
            status, _ = await self.request("PUT", path, data)
            self.assertEqual(status, 422)
        status, paid = await self.request("PUT", path, {"metodoPago": "YAPE", "fechaPago": "2026-08-29"})
        self.assertEqual(status, 200)
        self.assertEqual(paid["data"]["estado"], "PAGADO")
        self.assertEqual(paid["data"]["fechaPago"], "2026-08-29T00:00:00-05:00")
        self.assertEqual(paid["data"]["created_at"], expense["created_at"])
        status, _ = await self.request("PUT", path, {"metodoPago": "YAPE", "fechaPago": "2026-08-29"})
        self.assertEqual(status, 409)

    async def test_edit_preserves_audit_and_optional_fields(self):
        expense = await self.create(proveedorId=str(self.provider["_id"]),
                                    numeroComprobante="F001-000123", tipoComprobante="FACTURA",
                                    observaciones="Factura mensual")
        status, result = await self.request("PUT", f"/api/expenses/{expense['id']}",
            self.payload(monto="75.10", proveedorId=str(self.provider["_id"]),
                         numeroComprobante="F001-000123", tipoComprobante="FACTURA",
                         observaciones="Factura mensual"))
        self.assertEqual(status, 200)
        edited = result["data"]
        self.assertEqual(edited["created_at"], expense["created_at"])
        self.assertGreater(edited["updated_at"], expense["updated_at"])
        self.assertEqual(edited["usuarioId"], expense["usuarioId"])
        self.assertEqual(edited["observaciones"], "Factura mensual")
        self.assertEqual(edited["monto"], 75.1)
        self.assertIsInstance(self.expenses.documents[0]["monto"], Decimal128)

    async def test_filters_pagination_and_summary(self):
        await self.create(proveedorId=str(self.provider["_id"]), numeroComprobante="F001")
        await self.create(monto=120, metodoPago="TRANSFERENCIA")
        await self.create(monto=200, estado="PENDIENTE", metodoPago=None, fecha="2026-08-27")
        status, all_data = await self.request("GET", xpage=1)
        self.assertEqual(status, 200)
        self.assertEqual(len(all_data["data"][0]), 1)
        self.assertEqual(all_data["total"], 3)
        self.assertEqual(all_data["resumen"], {"registrados": 370, "pagados": 170,
                                              "pendientes": 200, "pagadosEfectivo": 50})
        cases = [({"fecha_desde": "2026-08-28", "fecha_hasta": "2026-08-28"}, 2),
                 ({"estado": "PENDIENTE"}, 1), ({"metodo_pago": "TRANSFERENCIA"}, 1),
                 ({"categoria": "Transporte"}, 0), ({"search": "Perú"}, 1),
                 ({"search": "F001"}, 1), ({"search": ".*"}, 0), ({"page": 20}, 3)]
        for filters, count in cases:
            with self.subTest(filters=filters):
                status, result = await self.request("GET", **filters)
                self.assertEqual(status, 200)
                self.assertEqual(result["total"], count)
        status, result = await self.request("GET", estado="PENDIENTE")
        self.assertEqual(result["resumen"]["pagadosEfectivo"], 0)
        self.assertEqual(result["resumen"]["pendientes"], 200)

    async def test_date_filter_includes_lima_day_boundaries(self):
        await self.create()
        doc = self.expenses.documents[0]
        doc["fecha"] = datetime(2026, 8, 29, 4, 59, 59, tzinfo=timezone.utc)
        _, result = await self.request("GET", fecha_desde="2026-08-28", fecha_hasta="2026-08-28")
        self.assertEqual(result["total"], 1)
        doc["fecha"] = datetime(2026, 8, 29, 5, 0, tzinfo=timezone.utc)
        _, result = await self.request("GET", fecha_desde="2026-08-28", fecha_hasta="2026-08-28")
        self.assertEqual(result["total"], 0)

    async def test_invalid_filters(self):
        for filters in ({"page": 0}, {"xpage": 101}, {"estado": "INVALIDO"},
                        {"metodo_pago": "INVALIDO"}, {"fecha_desde": "ayer"},
                        {"fecha_desde": "2026-09-01", "fecha_hasta": "2026-08-01"}):
            status, _ = await self.request("GET", **filters)
            self.assertEqual(status, 422)

    async def test_authentication_and_permissions(self):
        for token in (None, "bad-token"):
            status, _ = await self.request("GET", token=token)
            self.assertEqual(status, 401)
        status, _ = await self.request("POST", data=self.payload(), token=self.token_for(self.reader))
        self.assertEqual(status, 403)
        status, _ = await self.request("GET", token=self.token_for(self.reader))
        self.assertEqual(status, 200)

    async def test_existing_login_token_continues_working_after_expiration(self):
        token = create_access_token(
            {"sub": self.writer["username"], "local": 1}, timedelta(minutes=-45))
        for path in ("/api/expenses/options", "/api/expenses/providers", "/api/expenses"):
            status, result = await self.request("GET", path, token=token)
            self.assertEqual(status, 200, result)
        status, result = await self.request("POST", data=self.payload(
            estado="PENDIENTE", metodoPago=None), token=token)
        self.assertEqual(status, 201, result)
        expense = result["data"]
        self.assertEqual(expense["usuarioId"], str(self.writer["_id"]))
        path = f"/api/expenses/{expense['id']}"
        status, result = await self.request("GET", path, token=token)
        self.assertEqual(status, 200, result)
        status, result = await self.request("PUT", path, self.payload(
            estado="PENDIENTE", metodoPago=None, monto=75), token=token)
        self.assertEqual(status, 200, result)
        status, result = await self.request("PUT", path + "/pay",
            {"metodoPago": "EFECTIVO", "fechaPago": "2026-08-28"}, token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"]["created_at"], expense["created_at"])
        self.assertEqual(result["data"]["estado"], "PAGADO")
        status, result = await self.request("DELETE", path, token=token)
        self.assertEqual(status, 200, result)

    async def test_expired_token_still_respects_current_user_permissions_and_local(self):
        token = create_access_token(
            {"sub": self.reader["username"], "local": 1}, timedelta(minutes=-45))
        status, result = await self.request("GET", token=token)
        self.assertEqual(status, 200, result)
        status, _ = await self.request("POST", data=self.payload(), token=token)
        self.assertEqual(status, 403)
        expense = await self.create()
        foreign_token = create_access_token(
            {"sub": self.foreign["username"], "local": 2}, timedelta(minutes=-45))
        status, _ = await self.request("GET", f"/api/expenses/{expense['id']}", token=foreign_token)
        self.assertEqual(status, 404)
        status, _ = await self.request("GET", token=foreign_token, local=1)
        self.assertEqual(status, 403)
        self.auth.documents[1]["local"] = 2
        status, _ = await self.request("GET", token=token)
        self.assertEqual(status, 401)
        self.auth.documents = [self.writer, self.foreign]
        status, _ = await self.request("GET", token=token)
        self.assertEqual(status, 401)

    async def test_expiration_exception_does_not_accept_forged_unsigned_or_incomplete_tokens(self):
        claims = {"sub": self.writer["username"], "local": 1,
                  "exp": datetime.now(timezone.utc) - timedelta(minutes=45)}
        tokens = [
            service.jwt.encode(claims, "test-only-different-key", algorithm=service.ALGORITHM),
            service.jwt.encode(claims, None, algorithm="none"),
        ]
        for missing in ("sub", "local", "exp"):
            incomplete = {key: value for key, value in claims.items() if key != missing}
            tokens.append(service.jwt.encode(incomplete, service.SECRET_KEY, algorithm=service.ALGORITHM))
        for token in tokens:
            status, _ = await self.request("GET", token=token)
            self.assertEqual(status, 401)

    async def test_legacy_string_user_fields_use_the_existing_login_token(self):
        # Mongo guarda estos campos como texto; UserModel del login los convierte a int.
        self.auth.documents[0]["local"] = "1"
        self.auth.documents[0]["permissions"] = "1"
        for path in ("/api/expenses/options", "/api/expenses", "/api/expenses/providers"):
            status, result = await self.request("GET", path)
            self.assertEqual(status, 200, result)
        status, result = await self.request("POST", data=self.payload())
        self.assertEqual(status, 201, result)
        self.assertEqual(result["data"]["local"], 1)
        self.assertEqual(result["data"]["usuarioId"], str(self.writer["_id"]))

    async def test_legacy_string_reader_permissions_do_not_allow_writes(self):
        self.auth.documents[1]["local"] = "1"
        self.auth.documents[1]["permissions"] = "0"
        token = self.token_for(self.reader)
        status, result = await self.request("GET", token=token)
        self.assertEqual(status, 200, result)
        status, _ = await self.request("POST", data=self.payload(), token=token)
        self.assertEqual(status, 403)

    async def test_changed_or_invalid_user_local_does_not_accept_the_old_token(self):
        for local in ("2", "invalid", 1.5, None):
            self.auth.documents[0]["local"] = local
            status, _ = await self.request("GET")
            self.assertEqual(status, 401)
        self.auth.documents[0]["local"] = "1"
        self.auth.documents[0]["permissions"] = "invalid"
        status, _ = await self.request("POST", data=self.payload())
        self.assertEqual(status, 401)

    async def test_local_isolation_for_every_operation(self):
        expense = await self.create()
        other_token = self.token_for(self.foreign)
        for method, suffix, data in (("GET", "", None), ("PUT", "", self.payload()),
                                    ("DELETE", "", None),
                                    ("PUT", "/pay", {"metodoPago": "EFECTIVO", "fechaPago": "2026-08-28"})):
            status, _ = await self.request(method, f"/api/expenses/{expense['id']}{suffix}",
                                           data, token=other_token)
            self.assertEqual(status, 404)
        _, result = await self.request("GET", token=other_token)
        self.assertEqual(result["total"], 0)
        status, _ = await self.request("GET", local=2)
        self.assertEqual(status, 403)
        self.assertEqual(len(self.expenses.documents), 1)

    async def test_providers_options_and_deleted_supplier_snapshot(self):
        status, result = await self.request("GET", "/api/expenses/providers", search="Perú", xpage=1)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["total"], 1)
        status, _ = await self.request("POST", data=self.payload(proveedorId=str(self.other_provider["_id"])))
        self.assertEqual(status, 422)
        status, _ = await self.request("POST", data=self.payload(proveedorId="invalido"))
        self.assertEqual(status, 400)
        expense = await self.create(proveedorId=str(self.provider["_id"]))
        self.providers.documents = []
        status, result = await self.request("PUT", f"/api/expenses/{expense['id']}",
                                           self.payload(proveedorId=str(self.provider["_id"])))
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["proveedorNombre"], "Internet del Perú")
        status, options = await self.request("GET", "/api/expenses/options")
        self.assertEqual(status, 200)
        self.assertIn("PLIN", options["data"]["metodosPago"])

    async def test_detail_delete_and_invalid_ids(self):
        expense = await self.create()
        path = f"/api/expenses/{expense['id']}"
        status, result = await self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["id"], expense["id"])
        status, _ = await self.request("DELETE", path)
        self.assertEqual(status, 200)
        status, detail = await self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertTrue(detail["data"]["anulado"])
        self.assertEqual(len(self.expenses.documents), 1)
        _, listing = await self.request("GET")
        self.assertEqual(listing["total"], 0)
        status, _ = await self.request("GET", "/api/expenses/not-an-id")
        self.assertEqual(status, 400)

    async def test_naive_mongo_dates_are_serialized_as_utc_in_lima(self):
        expense = await self.create()
        stored = self.expenses.documents[0]
        for field in ("fecha", "fechaPago", "created_at", "updated_at"):
            stored[field] = stored[field].replace(tzinfo=None)
        status, result = await self.request("GET", f"/api/expenses/{expense['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["fecha"], "2026-08-28T00:00:00-05:00")
        self.assertEqual(result["data"]["created_at"], expense["created_at"])

    async def test_decimal_totals_and_zero_results(self):
        await self.create(monto="0.10")
        await self.create(monto="0.20")
        _, result = await self.request("GET")
        self.assertEqual(result["resumen"]["registrados"], 0.3)
        _, result = await self.request("GET", search="sin coincidencias")
        self.assertEqual(result["data"], [[]])
        self.assertEqual(result["resumen"]["registrados"], 0)


if __name__ == "__main__":
    unittest.main()

