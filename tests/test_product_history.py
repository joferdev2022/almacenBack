"""Historial con persistencia en memoria. No conecta a MongoDB."""
import json
import unittest
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import bcrypt
from bson import ObjectId
from fastapi import FastAPI, HTTPException

from memory_db import MemoryDatabase, database_patches
from app.models.product_model import productModel
from app.models.sales_model import saleModel
from app.routes import products_route
from app.services import product_history_service as history, products_service as products, sales_service as sales
from app.services.auth_service import create_access_token
from config import settings

TEST_PIN = '2468'
TEST_HASH = bcrypt.hashpw(TEST_PIN.encode(), bcrypt.gensalt(rounds=4)).decode()


class ProductHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        for item in database_patches(self.db):
            item.start()
            self.addCleanup(item.stop)
        configured = patch.object(settings, 'PRODUCT_HISTORY_PIN_HASH', TEST_HASH)
        configured.start()
        self.addCleanup(configured.stop)
        history._attempts.clear()
        history.ensure_indexes()
        self.user = {'_id': ObjectId(), 'username': 'tienda-test', 'local': 1, 'permissions': 0}
        self.foreign = {'_id': ObjectId(), 'username': 'otro-local', 'local': 2, 'permissions': 0}
        for user in (self.user, self.foreign):
            self.db.authDb.insert_one(user)
        self.product = productModel(nombre='Arroz', descripcion='', categoria='Abarrotes',
            precioCompra=3, precioVenta=5, cantidadEnStock=100, unidadDeMedida='Bolsa', local=1).model_dump(by_alias=True)
        self.product.pop('_id', None)
        self.product['_id'] = ObjectId()
        self.db.productsDb.insert_one(self.product)
        self.api = FastAPI()
        self.api.include_router(products_route.router, prefix='/api')

    def result(self):
        return history.retrieve_history(str(self.product['_id']), TEST_PIN, self.user)

    def stock(self):
        return self.db.productsDb.find_one({'_id': self.product['_id']})['cantidadEnStock']

    def sale_data(self, quantity=1, items=None):
        rows = items if items is not None else [{'productoId': str(self.product['_id']), 'cantidad': quantity,
            'precioUnitario': 5, 'precioBuy': 3, 'productName': 'Arroz'}]
        return saleModel(nombreVendedor='Vendedor', nombreCliente='Cliente', direccionCliente='',
            precioTotal=sum(row['cantidad'] * row['precioUnitario'] for row in rows),
            estado='credito', paymentMethod=None, local=1, productos=rows)

    async def request(self, path, data, user='default', method='POST', authenticated=True):
        selected = self.user if user == 'default' else user
        token = create_access_token({'sub': selected['username'], 'local': selected['local']},
                                    expires_delta=timedelta(minutes=5))
        body, messages = json.dumps(data).encode(), []
        async def receive():
            return {'type': 'http.request', 'body': body, 'more_body': False}
        async def send(message):
            messages.append(message)
        headers = [(b'content-type', b'application/json')]
        if authenticated:
            headers.append((b'authorization', ('Bearer ' + token).encode()))
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method,
            'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'root_path': '', 'query_string': b'',
            'headers': headers, 'client': ('127.0.0.1', 12345), 'server': ('test', 80)}
        await self.api(scope, receive, send)
        return next(m['status'] for m in messages if m['type'] == 'http.response.start'), json.loads(
            b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))

    async def test_manual_edit_records_only_changed_fields_and_actor(self):
        await products.update_product_by_id(str(self.product['_id']),
            {'cantidadEnStock': 90, 'precioVenta': 6, 'nombre': 'Arroz'}, self.user)
        event = self.result()['eventos'][0]
        self.assertEqual(self.stock(), 90)
        self.assertEqual(event['accion'], 'EDICION_MANUAL')
        self.assertEqual(event['usuarioId'], str(self.user['_id']))
        self.assertEqual(event['usuarioNombre'], self.user['username'])
        self.assertEqual(event['cambios'], [
            {'campo': 'precioVenta', 'antes': 5, 'despues': 6},
            {'campo': 'cantidadEnStock', 'antes': 100, 'despues': 90}])
        self.assertTrue(event['fecha'].endswith('-05:00'))
        self.assertNotIn('pin', event)

    async def test_retains_every_record_but_reads_three_newest_with_stable_order(self):
        for quantity in range(99, 92, -1):
            await products.update_product_by_id(str(self.product['_id']), {'cantidadEnStock': quantity}, self.user)
        same_date = self.db.productHistoryDb.documents[0]['fecha']
        for row in self.db.productHistoryDb.documents:
            row['fecha'] = same_date
        result = self.result()
        self.assertEqual(result['total'], 7)
        self.assertEqual(len(self.db.productHistoryDb.documents), 7)
        self.assertEqual([e['cambios'][0]['despues'] for e in result['eventos']], [93, 94, 95])
        self.assertEqual(result['producto']['cantidadEnStock'], 93)

    async def test_noop_does_not_create_noise_and_legacy_product_starts_empty(self):
        self.assertEqual(self.result()['eventos'], [])
        await products.update_product_by_id(str(self.product['_id']), {'nombre': 'Arroz'}, self.user)
        self.assertEqual(self.result()['total'], 0)

    async def test_manual_write_rolls_back_if_history_insert_fails(self):
        with patch.object(self.db.productHistoryDb, 'insert_one', side_effect=RuntimeError('fallo de prueba')):
            with self.assertRaises(RuntimeError):
                await products.update_product_by_id(str(self.product['_id']), {'cantidadEnStock': 3}, self.user)
        self.assertEqual(self.stock(), 100)
        self.assertEqual(self.result()['total'], 0)

    async def test_creation_and_deletion_keep_history_even_after_product_removal(self):
        values = deepcopy(self.product)
        values.pop('_id')
        created = await products.add_product(values, self.user)
        product_id = created['id']
        await products.delete_product_by_id(product_id, self.user)
        rows = list(self.db.productHistoryDb.find({'productoId': ObjectId(product_id)}))
        self.assertEqual([e['accion'] for e in rows], ['CREACION', 'ELIMINACION'])
        self.assertIsNone(self.db.productsDb.find_one({'_id': ObjectId(product_id)}))

    async def test_identity_is_from_token_and_legacy_calls_are_labelled(self):
        values = {k: v for k, v in self.product.items() if k != '_id'}
        payload = productModel(**{**values, 'cantidadEnStock': 95}).model_dump(mode='json', by_alias=True)
        payload['usuarioNombre'] = 'Nombre inventado'
        status, _ = await self.request(f"/api/products/{self.product['_id']}", payload, method='PUT')
        self.assertEqual(status, 200)
        self.assertEqual(self.result()['eventos'][0]['usuarioNombre'], self.user['username'])
        await products.update_product_by_id(str(self.product['_id']), {'cantidadEnStock': 94})
        self.assertEqual(self.result()['eventos'][0]['usuarioNombre'], 'Sin usuario identificado')

    def test_sale_edit_annulment_and_retries_do_not_duplicate_stock_or_history(self):
        key = str(uuid4())
        sale = sales.add_sale(self.sale_data(), self.user, key)
        sales.add_sale(self.sale_data(), self.user, key)
        self.assertEqual(self.stock(), 99)
        self.assertEqual(self.result()['total'], 1)
        edit_key = str(uuid4())
        sales.update_sale_by_id(sale['id'], self.sale_data(3), self.user, edit_key)
        sales.update_sale_by_id(sale['id'], self.sale_data(3), self.user, edit_key)
        self.assertEqual(self.stock(), 97)
        sales.update_sale_by_id(sale['id'], self.sale_data(3), self.user, str(uuid4()))
        annul_key = str(uuid4())
        sales.delete_sale_by_id(sale['id'], self.user, annul_key, 'Venta duplicada')
        sales.delete_sale_by_id(sale['id'], self.user, annul_key, 'Venta duplicada')
        self.assertEqual(self.stock(), 100)
        result = self.result()
        self.assertEqual(result['total'], 3)
        self.assertEqual([e['accion'] for e in result['eventos']], ['ANULACION_VENTA', 'EDICION_VENTA', 'VENTA'])
        self.assertEqual(result['eventos'][0]['motivo'], 'Venta duplicada')
        self.assertTrue(all(e['ventaId'] == sale['id'] for e in result['eventos']))

    def test_failed_sale_rolls_back_stock_history_and_sale(self):
        for collection, method in ((self.db.productHistoryDb, 'insert_one'), (self.db.salesDb, 'insert_one')):
            with self.subTest(collection=collection.full_name), patch.object(collection, method, side_effect=RuntimeError('fallo')):
                with self.assertRaises(RuntimeError):
                    sales.add_sale(self.sale_data(), self.user, str(uuid4()))
                self.assertEqual(self.stock(), 100)
                self.assertEqual(self.db.productHistoryDb.documents, [])
                self.assertEqual(self.db.salesDb.documents, [])

    def test_insufficient_stock_later_in_sale_rolls_back_earlier_product_and_history(self):
        items = self.sale_data().model_dump()['productos']
        items.append({**items[0], 'productoId': str(ObjectId())})
        with self.assertRaises(HTTPException) as failure:
            sales.add_sale(self.sale_data(items=items), self.user, str(uuid4()))
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(self.stock(), 100)
        self.assertEqual(self.db.productHistoryDb.documents, [])

    async def test_history_requires_login_pin_and_current_local_without_roles(self):
        path = f"/api/products/{self.product['_id']}/history"
        self.assertEqual((await self.request(path, {'pin': TEST_PIN}, authenticated=False))[0], 401)
        self.assertEqual((await self.request(path, {'pin': '0000'}))[0], 403)
        self.assertEqual((await self.request(path, {'pin': 'abcd'}))[0], 422)
        self.assertEqual((await self.request(path, {'pin': TEST_PIN}, user=self.foreign))[0], 404)
        status, response = await self.request(path, {'pin': TEST_PIN, 'local': 2})
        self.assertEqual(status, 200)
        self.assertEqual(response['data']['producto']['nombre'], 'Arroz')

    def test_no_default_pin_and_attempts_are_limited_across_products(self):
        with patch.object(settings, 'PRODUCT_HISTORY_PIN_HASH', None):
            with self.assertRaises(HTTPException) as failure:
                self.result()
            self.assertEqual(failure.exception.status_code, 503)
        for _ in range(5):
            with self.assertRaises(HTTPException) as failure:
                history.retrieve_history(str(ObjectId()), '0000', self.user)
            self.assertEqual(failure.exception.status_code, 403)
        with self.assertRaises(HTTPException) as failure:
            self.result()
        self.assertEqual(failure.exception.status_code, 429)

    def test_history_has_no_ttl_or_capped_retention(self):
        keys, options = self.db.productHistoryDb.indexes[0]
        self.assertEqual(keys, [('local', 1), ('productoId', 1), ('fecha', -1), ('_id', -1)])
        self.assertNotIn('expireAfterSeconds', options)
