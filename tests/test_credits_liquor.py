import unittest
from datetime import date
from unittest.mock import patch

from bson import ObjectId
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from memory_db import MemoryDatabase
from app.models.saleLiquor_model import SaleLiquorRequestModel
from app.services import creditsLiquor_service, salesLiquor_service


class CreditsLiquorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.sales = self.db.sales_liquorDb
        self.products = self.db.products_liquorDb
        self.patches = [
            patch.object(salesLiquor_service, "sales_liquorDb", self.sales),
            patch.object(salesLiquor_service, "products_liquorDb", self.products),
            patch.object(creditsLiquor_service, "sales_liquorDb", self.sales),
        ]
        for current_patch in self.patches:
            current_patch.start()
            self.addCleanup(current_patch.stop)

        self.product_id = ObjectId()
        self.products.insert_one(
            {"_id": self.product_id, "local": 1, "cantidadEnStock": 20}
        )

    def credit_payload(self):
        return {
            "local": 1,
            "estado": "credito",
            "condicionPago": "credito",
            "clienteCredito": {"nombre": "Juan Pérez", "telefono": "999888777"},
            "fechaVencimiento": date(2026, 9, 30),
            "pago": {
                "tipo": "credito",
                "total": 12000,
                "pagado": 0,
                "saldoPendiente": 12000,
                "estadoPago": "pendiente",
                "pagos": [],
            },
            "productos": [
                {
                    "productoId": str(self.product_id),
                    "skuId": "sixpack",
                    "cantidad": 2,
                    "equivalenciaUnidades": 6,
                    "precioCompraUnitario": 500,
                    "precioVentaUnitario": 6000,
                    "nombreProducto": "Producto de prueba",
                    "skuNombre": "Six pack",
                }
            ],
        }

    async def create_credit(self):
        model = SaleLiquorRequestModel(**self.credit_payload())
        return await salesLiquor_service.add_sale(jsonable_encoder(model))

    async def test_credit_sale_has_customer_balance_and_no_initial_payment(self):
        sale = await self.create_credit()
        self.assertEqual(sale["condicionPago"], "credito")
        self.assertEqual(sale["clienteCredito"]["nombre"], "Juan Pérez")
        self.assertEqual(sale["pago"]["pagado"], 0)
        self.assertEqual(sale["pago"]["saldoPendiente"], 12000)
        self.assertEqual(sale["pago"]["pagos"], [])
        self.assertEqual(self.products.documents[0]["cantidadEnStock"], 8)

    async def test_partial_and_full_payments_are_appended(self):
        sale = await self.create_credit()
        partial = await creditsLiquor_service.add_credit_payment_liquor(
            sale["id"],
            {"monto": 4000, "metodo": "yape", "referencia": "OP-1"},
        )
        self.assertEqual(partial["pago"]["pagado"], 4000)
        self.assertEqual(partial["pago"]["saldoPendiente"], 8000)
        self.assertEqual(partial["pago"]["estadoPago"], "parcial")
        self.assertEqual(partial["pago"]["pagos"][0]["metodo"], "yape")

        paid = await creditsLiquor_service.add_credit_payment_liquor(
            sale["id"], {"monto": 8000, "metodo": "efectivo"}
        )
        self.assertEqual(paid["pago"]["saldoPendiente"], 0)
        self.assertEqual(paid["pago"]["estadoPago"], "pagado")
        self.assertEqual(len(paid["pago"]["pagos"]), 2)

        listing = await creditsLiquor_service.retrieve_credits_liquor(
            1, 10, 1, status="pagado"
        )
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["summary"]["totalPagado"], 12000)

    async def test_payment_cannot_exceed_balance(self):
        sale = await self.create_credit()
        with self.assertRaises(HTTPException) as error:
            await creditsLiquor_service.add_credit_payment_liquor(
                sale["id"], {"monto": 12001, "metodo": "efectivo"}
            )
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.sales.documents[0]["pago"]["pagado"], 0)

    async def test_credit_with_payments_cannot_be_deleted(self):
        sale = await self.create_credit()
        await creditsLiquor_service.add_credit_payment_liquor(
            sale["id"], {"monto": 4000, "metodo": "yape"}
        )

        with self.assertRaises(HTTPException) as error:
            await salesLiquor_service.delete_sale_by_id(sale["id"])

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.sales.documents), 1)
        self.assertEqual(self.products.documents[0]["cantidadEnStock"], 8)


if __name__ == "__main__":
    unittest.main()
