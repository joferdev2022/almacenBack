"""Dosificaciones con persistencia aislada: permisos, concurrencia y conservación con Excel."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from memory_db import MemoryDatabase, database_patches
from test_product_excel import complete, excel
from app.models.product_dosage_model import ProductDosageUpdate
from app.routes import products_route
from app.services import product_dosage_service as dosage, products_service as products
from app.services.expenses_service import get_expense_user


ENTRY = {'cultivo': 'Uso de la etiqueta', 'objetivo': 'Objetivo indicado', 'dosis': 'Dosis de ficha técnica',
         'baseAplicacion': 'Referencia de la etiqueta', 'aplicacion': 'Forma indicada',
         'observaciones': 'Información registrada', 'fuente': 'Ficha del producto'}


class ProductDosageTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        for binding in database_patches(self.db) + [patch.object(dosage, 'productsDb', self.db.productsDb)]:
            binding.start()
            self.addCleanup(binding.stop)
        self.writer = {'_id': ObjectId(), 'username': 'admin', 'local': 1, 'permissions': 1}
        self.reader = {**self.writer, '_id': ObjectId(), 'username': 'lector', 'permissions': 0}
        self.foreign = {**self.writer, '_id': ObjectId(), 'local': 2}
        self.product = {'_id': ObjectId(), 'local': 1, 'nombre': 'Producto de prueba', 'unidadDeMedida': '50 KG',
                        'cantidadEnStock': 15, 'precioCompra': 10, 'precioVenta': 20, 'categoria': '',
                        'descripcion': '', 'proveedorId': None, 'fechaDeCaducidad': None,
                        'fechaDeCreacion': datetime(2026, 1, 1)}
        self.db.productsDb.insert_one(self.product)
        self.id = str(self.product['_id'])
        self.api = FastAPI()
        self.api.include_router(products_route.router, prefix='/api')
        self.current_user = self.writer
        async def user():
            return self.current_user
        self.api.dependency_overrides[get_expense_user] = user

    def data(self, entries=None, version=0):
        return ProductDosageUpdate(version=version, dosificaciones=[deepcopy(ENTRY)] if entries is None else entries)

    def saved(self):
        return self.db.productsDb.find_one({'_id': self.product['_id']})

    def request(self, method='GET', body=None, product_id=None):
        async def call():
            path = f'/api/products/{product_id or self.id}/dosages'
            messages = []
            raw = b'' if body is None else json.dumps(body).encode()
            async def receive():
                return {'type': 'http.request', 'body': raw, 'more_body': False}
            async def send(message):
                messages.append(message)
            scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method,
                     'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'root_path': '', 'query_string': b'',
                     'headers': [(b'content-type', b'application/json')], 'client': ('127.0.0.1', 12345), 'server': ('test', 80)}
            await self.api(scope, receive, send)
            return next(m['status'] for m in messages if m['type'] == 'http.response.start'), json.loads(
                b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))
        return complete(call())

    def test_old_products_have_an_empty_readable_dosage_without_writes(self):
        for user in (self.writer, self.reader):
            response = dosage.retrieve_dosages(self.id, user)
            self.assertEqual(response['dosificaciones'], [])
            self.assertEqual(response['version'], 0)
            self.assertEqual(response['producto']['id'], self.id)
            self.assertEqual(response['puedeEditar'], user['permissions'] == 1)
            self.assertIsNone(response['actualizadoEn'])
            self.assertIsNone(response['actualizadoPor'])
        self.assertEqual(self.saved(), self.product)

    def test_save_multiple_uses_records_author_time_and_modifies_only_dosage_fields(self):
        instant = datetime(2026, 11, 11, 0, 30, tzinfo=timezone.utc)
        entries = [ENTRY, {**ENTRY, 'cultivo': 'Otro uso', 'observaciones': ''}]
        with patch.object(dosage, 'datetime') as clock:
            clock.now.return_value = instant
            result = dosage.save_dosages(self.id, self.data(entries), self.writer)
            clock.now.assert_called_once_with(timezone.utc)
        saved = self.saved()
        self.assertEqual({key: saved[key] for key in self.product}, self.product)
        self.assertEqual(saved['dosificaciones'], entries)
        self.assertEqual(saved['dosificacionesVersion'], 1)
        self.assertEqual(saved['dosificacionesActualizadasEn'], instant)
        self.assertEqual(saved['dosificacionesActualizadasPor']['_id'], self.writer['_id'])
        self.assertEqual(result['actualizadoPor'], {'id': str(self.writer['_id']), 'nombre': 'admin'})
        self.assertEqual(result['actualizadoEn'], '2026-11-10T19:30:00-05:00')
        self.assertEqual(dosage.retrieve_dosages(self.id, self.writer)['dosificaciones'], entries)

    def test_reader_cannot_write_even_calling_the_service_directly(self):
        with self.assertRaises(HTTPException) as failure:
            dosage.save_dosages(self.id, self.data(), self.reader)
        self.assertEqual(failure.exception.status_code, 403)
        self.assertEqual(self.saved(), self.product)

    def test_other_local_cannot_read_or_write_a_known_product_id(self):
        for action in (lambda: dosage.retrieve_dosages(self.id, self.foreign),
                       lambda: dosage.save_dosages(self.id, self.data(), self.foreign)):
            with self.assertRaises(HTTPException) as failure:
                action()
            self.assertEqual(failure.exception.status_code, 404)
        self.assertEqual(self.saved(), self.product)

    def test_unknown_and_invalid_ids_have_explicit_errors(self):
        for identifier, expected in (('invalid', 400), (str(ObjectId()), 404)):
            with self.subTest(identifier=identifier):
                for action in (lambda: dosage.retrieve_dosages(identifier, self.writer),
                               lambda: dosage.save_dosages(identifier, self.data(), self.writer)):
                    with self.assertRaises(HTTPException) as failure:
                        action()
                    self.assertEqual(failure.exception.status_code, expected)

    def test_required_fields_reject_whitespace_and_lengths_and_extra_fields_are_checked(self):
        for field in ('cultivo', 'dosis', 'baseAplicacion'):
            for value in ('', '  '):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    self.data([{**ENTRY, field: value}])
        for field, limit in (('cultivo', 150), ('objetivo', 250), ('dosis', 250), ('baseAplicacion', 200),
                             ('aplicacion', 500), ('observaciones', 2000), ('fuente', 500)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.data([{**ENTRY, field: 'x' * (limit + 1)}])
        for payload in ({'version': 0, 'dosificaciones': [ENTRY], 'local': 2},
                        {'version': 0, 'dosificaciones': [{**ENTRY, 'cantidadEnStock': 999}]},
                        {'version': False, 'dosificaciones': [ENTRY]}, {'dosificaciones': [ENTRY]}):
            with self.assertRaises(ValidationError):
                ProductDosageUpdate.model_validate(payload)

    def test_optional_fields_can_be_empty_and_values_are_trimmed(self):
        data = self.data([{'cultivo': ' Uso general ', 'dosis': ' Según etiqueta ', 'baseAplicacion': ' Base indicada '}])
        result = dosage.save_dosages(self.id, data, self.writer)
        self.assertEqual(result['dosificaciones'][0], {
            'cultivo': 'Uso general', 'dosis': 'Según etiqueta', 'baseAplicacion': 'Base indicada',
            'objetivo': '', 'aplicacion': '', 'observaciones': '', 'fuente': ''})

    def test_entry_limit_and_explicit_empty_list_to_clear_dosages(self):
        self.assertEqual(len(self.data([ENTRY] * 50).dosificaciones), 50)
        with self.assertRaises(ValidationError):
            self.data([ENTRY] * 51)
        dosage.save_dosages(self.id, self.data(), self.writer)
        result = dosage.save_dosages(self.id, self.data([], version=1), self.writer)
        self.assertEqual(result['dosificaciones'], [])
        self.assertEqual(result['version'], 2)
        self.assertEqual(self.saved()['cantidadEnStock'], 15)

    def test_stale_version_cannot_overwrite_another_saved_version(self):
        dosage.save_dosages(self.id, self.data(), self.writer)
        original = deepcopy(self.saved())
        with self.assertRaises(HTTPException) as failure:
            dosage.save_dosages(self.id, self.data([{**ENTRY, 'dosis': 'Otro texto'}]), self.writer)
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(self.saved(), original)

    def test_concurrent_update_between_read_and_write_is_rejected_atomically(self):
        update = self.db.productsDb.update_one
        def concurrent(query, values):
            update({'_id': self.product['_id']}, {'$set': {'dosificacionesVersion': 1,
                   'dosificaciones': [{**ENTRY, 'dosis': 'Cambio de otra persona'}]}})
            return update(query, values)
        with patch.object(self.db.productsDb, 'update_one', side_effect=concurrent):
            with self.assertRaises(HTTPException) as failure:
                dosage.save_dosages(self.id, self.data(), self.writer)
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(self.saved()['dosificaciones'][0]['dosis'], 'Cambio de otra persona')
        self.assertNotIn('dosificacionesActualizadasPor', self.saved())

    def test_deleted_product_during_save_returns_not_found(self):
        def deleted(*args, **kwargs):
            self.db.productsDb.delete_one({'_id': self.product['_id']})
            return SimpleNamespace(matched_count=0)
        with patch.object(self.db.productsDb, 'update_one', side_effect=deleted):
            with self.assertRaises(HTTPException) as failure:
                dosage.save_dosages(self.id, self.data(), self.writer)
        self.assertEqual(failure.exception.status_code, 404)

    def test_manual_product_edit_preserves_dosage_and_its_metadata(self):
        dosage.save_dosages(self.id, self.data(), self.writer)
        original = {key: value for key, value in self.saved().items() if key.startswith('dosificaciones')}
        self.assertTrue(complete(products.update_product_by_id(self.id, {'nombre': 'Nombre actualizado', 'precioVenta': 25}, self.writer)))
        self.assertEqual({key: value for key, value in self.saved().items() if key.startswith('dosificaciones')}, original)

    def test_excel_updates_and_zeroing_omitted_products_preserve_dosages(self):
        dosage.save_dosages(self.id, self.data(), self.writer)
        absent = {**self.saved(), '_id': ObjectId(), 'nombre': 'Ausente del Excel'}
        self.db.productsDb.insert_one(absent)
        original = {key: value for key, value in self.saved().items() if key.startswith('dosificaciones')}
        payload = excel([{'CODIGO': self.id, 'PRODUCTO': self.product['nombre'], 'PRESENTACION': '50 KG',
                          'CANTIDAD': 22, 'P. UNITARIO': 10, 'P. VENTA': 20}])
        result = complete(products.upload_excel(payload, 1))
        self.assertEqual((result['updated_count'], result['zeroed_count']), (1, 1))
        self.assertEqual(self.saved()['cantidadEnStock'], 22)
        self.assertEqual({key: value for key, value in self.saved().items() if key.startswith('dosificaciones')}, original)
        omitted = self.db.productsDb.find_one({'_id': absent['_id']})
        self.assertEqual(omitted['cantidadEnStock'], 0)
        self.assertEqual({key: value for key, value in omitted.items() if key.startswith('dosificaciones')}, original)

    def test_api_read_and_write_permissions_and_serialized_metadata(self):
        status, body = self.request()
        self.assertEqual((status, body['data']['dosificaciones']), (200, []))
        status, body = self.request('PUT', self.data().model_dump())
        self.assertEqual((status, body['data']['version']), (200, 1))
        self.assertEqual(body['data']['actualizadoPor']['nombre'], 'admin')
        self.current_user = self.reader
        status, body = self.request()
        self.assertEqual(status, 200)
        self.assertFalse(body['data']['puedeEditar'])
        self.assertEqual(self.request('PUT', self.data(version=1).model_dump())[0], 403)
        self.current_user = self.foreign
        self.assertEqual(self.request()[0], 404)
        self.assertEqual(self.request('PUT', self.data(version=1).model_dump())[0], 404)

    def test_api_rejects_invalid_payloads_without_modifying_product(self):
        for payload in ({'version': 0, 'dosificaciones': [{**ENTRY, 'dosis': ''}]},
                        {'version': 0, 'dosificaciones': [ENTRY], 'local': 2},
                        {'dosificaciones': [ENTRY]}, {'version': 0, 'dosificaciones': [ENTRY] * 51}):
            self.assertEqual(self.request('PUT', payload)[0], 422)
        self.assertEqual(self.saved(), self.product)

    def test_anonymous_api_requests_require_authentication(self):
        self.api.dependency_overrides.clear()
        self.assertEqual(self.request()[0], 401)
        self.assertEqual(self.request('PUT', self.data().model_dump())[0], 401)
