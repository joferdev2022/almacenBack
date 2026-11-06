"""Conteo Excel con MongoDB en memoria: nunca conecta a la base de datos real."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from tempfile import SpooledTemporaryFile
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from openpyxl import Workbook, load_workbook

from memory_db import MemoryDatabase
from app.routes import products_route
from app.services import products_service as products
from app.services.product_excel_service import EXCEL_COLUMNS, prepare_import


def complete(coroutine):
    # These handlers perform synchronous DB calls and in-memory file reads.
    # No event-loop/network connection is needed for the isolated assertions.
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    coroutine.close()
    raise AssertionError('Unexpected asynchronous I/O in the isolated test')


def excel(rows, headers=EXCEL_COLUMNS):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Productos'
    sheet.append(list(headers))
    for row in rows:
        sheet.append([row.get(column) for column in headers])
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


class ProductExcelTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.product = {'_id': ObjectId(), 'nombre': 'Arroz', 'unidadDeMedida': 'KG',
                        'cantidadEnStock': 8, 'precioCompra': 3, 'precioVenta': 5, 'local': 1,
                        'descripcion': 'Anterior', 'categoria': 'Alimentos', 'marca': 'Marca',
                        'proveedorId': 'proveedor', 'fechaDeCaducidad': None,
                        'fechaDeCreacion': datetime(2020, 1, 1)}
        self.absent = {**self.product, '_id': ObjectId(), 'nombre': 'Sal', 'cantidadEnStock': 9}
        self.foreign = {**self.product, '_id': ObjectId(), 'nombre': 'Otro local', 'local': 2}
        for item in (self.product, self.absent, self.foreign):
            self.db.productsDb.insert_one(item)
        for name in ('productsDb', 'productImportsDb'):
            binding = patch.object(products, name, getattr(self.db, name))
            binding.start()
            self.addCleanup(binding.stop)
        self.api = FastAPI()
        self.api.include_router(products_route.router, prefix='/api')

    def row(self, **overrides):
        return {'CODIGO': str(self.product['_id']), 'CANTIDAD': 12, 'PRODUCTO': 'Arroz',
                'PRESENTACION': 'KG', 'P. UNITARIO': 3, 'P. VENTA': 5, **overrides}

    def preview(self, rows, headers=EXCEL_COLUMNS):
        return complete(products.preview_excel(excel(rows, headers), 1))

    def assert_rejected_without_writes(self, rows, headers=EXCEL_COLUMNS):
        original = deepcopy(self.db.productsDb.documents)
        original_imports = deepcopy(self.db.productImportsDb.documents)
        with patch.object(self.db.productsDb, 'update_one', wraps=self.db.productsDb.update_one) as update, \
             patch.object(self.db.productsDb, 'insert_one', wraps=self.db.productsDb.insert_one) as insert:
            with self.assertRaises(HTTPException) as failure:
                complete(products.upload_excel(excel(rows, headers), 1))
            self.assertEqual(failure.exception.status_code, 422)
            update.assert_not_called()
            insert.assert_not_called()
        self.assertEqual(self.db.productsDb.documents, original)
        self.assertEqual(self.db.productImportsDb.documents, original_imports)
        return failure.exception.detail['errors']

    def test_export_code_is_first_and_quantity_second_and_codes_are_text(self):
        result = complete(products.download_excel(1))
        book = load_workbook(BytesIO(result['file']))
        self.addCleanup(book.close)
        sheet = book['Productos']
        self.assertEqual([cell.value for cell in sheet[1]], list(EXCEL_COLUMNS))
        self.assertEqual(sheet['A2'].value, str(self.product['_id']))
        self.assertEqual(sheet['A2'].data_type, 's')
        self.assertEqual(sheet['B2'].value, 8)

    def test_preview_has_no_writes_and_lists_missing_products_to_zero(self):
        original = deepcopy(self.db.productsDb.documents)
        result = self.preview([self.row()])
        self.assertTrue(result['valid'])
        self.assertEqual((result['updated_count'], result['inserted_count'], result['zeroed_count']), (1, 0, 1))
        self.assertEqual(result['preview'][0]['stock_before'], 8)
        self.assertEqual(result['preview'][0]['stock_after'], 12)
        self.assertEqual(result['preview'][1]['action'], 'zero')
        self.assertEqual(result['preview'][1]['code'], str(self.absent['_id']))
        self.assertEqual(self.db.productsDb.documents, original)
        self.assertEqual(self.db.productImportsDb.count_documents({}), 0)
        self.assertFalse(any(key.startswith('_') for key in result))

    def test_blank_quantity_becomes_zero_and_optional_fields_may_be_blank(self):
        for value in (None, '', '  '):
            with self.subTest(value=value):
                result = self.preview([self.row(CANTIDAD=value)])
                self.assertTrue(result['valid'])
                self.assertEqual(result['preview'][0]['stock_after'], 0)

    def test_required_values_are_reported_for_every_row_before_any_write(self):
        rows = [self.row(PRODUCTO='', **{'P. UNITARIO': None}),
                self.row(CODIGO='', PRODUCTO='Nuevo', PRESENTACION='', **{'P. VENTA': '   '})]
        errors = self.assert_rejected_without_writes(rows)
        positions = {(e['row'], e['column']) for e in errors}
        self.assertTrue({(2, 'PRODUCTO'), (2, 'P. UNITARIO'), (3, 'PRESENTACION'), (3, 'P. VENTA')} <= positions)

    def test_blank_prices_also_reject_existing_products(self):
        for field in ('P. UNITARIO', 'P. VENTA'):
            with self.subTest(field=field):
                errors = self.assert_rejected_without_writes([self.row(**{field: None})])
                self.assertTrue(any(e['column'] == field for e in errors))

    def test_zero_prices_are_valid_and_not_confused_with_blanks(self):
        result = self.preview([self.row(**{'P. UNITARIO': 0, 'P. VENTA': 0})])
        self.assertTrue(result['valid'])

    def test_invalid_numbers_negative_fractional_and_formulas_are_not_silently_zeroed(self):
        for field, value in [('CANTIDAD', -1), ('CANTIDAD', 1.5), ('CANTIDAD', 'abc'),
                             ('CANTIDAD', '=1+2'), ('P. UNITARIO', 'S/ 30'),
                             ('P. VENTA', -5), ('P. VENTA', 'NaN'), ('P. VENTA', True)]:
            with self.subTest(field=field, value=value):
                errors = self.assert_rejected_without_writes([self.row(**{field: value})])
                self.assertTrue(any(e['column'] == field for e in errors))

    def test_duplicate_name_presentation_blocks_both_rows_even_with_different_codes(self):
        errors = self.assert_rejected_without_writes([
            self.row(), self.row(CODIGO='', PRODUCTO=' ARROZ ', PRESENTACION='Kilogramo')])
        self.assertEqual({e['row'] for e in errors if e['column'] == 'PRODUCTO / PRESENTACION'}, {2, 3})

    def test_same_name_different_presentation_is_a_different_product(self):
        result = self.preview([self.row(), self.row(CODIGO='', PRESENTACION='250 GR')])
        self.assertTrue(result['valid'])
        self.assertEqual((result['inserted_count'], result['updated_count']), (1, 1))

    def test_duplicate_code_or_resolved_id_cannot_update_a_product_twice(self):
        errors = self.assert_rejected_without_writes([
            self.row(PRODUCTO='Arroz nuevo'), self.row(CODIGO='')])
        self.assertTrue(any(e['column'] == 'CODIGO' and e['row'] == 3 for e in errors))

    def test_foreign_or_unknown_code_blocks_import(self):
        for code in (str(self.foreign['_id']), str(ObjectId())):
            with self.subTest(code=code):
                errors = self.assert_rejected_without_writes([self.row(CODIGO=code)])
                self.assertTrue(any(e['column'] == 'CODIGO' for e in errors))

    def test_existing_catalog_duplicate_cannot_be_merged_silently(self):
        duplicate = {**self.product, '_id': ObjectId(), 'unidadDeMedida': 'KILOGRAMO'}
        self.db.productsDb.insert_one(duplicate)
        for row in (self.row(CODIGO=''), self.row()):
            with self.subTest(code=row['CODIGO']):
                errors = self.assert_rejected_without_writes([row])
                conflict = next(error for error in errors if error['column'] == 'PRODUCTO / PRESENTACION')
                self.assertIn('Arroz / KG', conflict['message'])
                self.assertEqual({item['code'] for item in conflict['conflicts']},
                                 {str(self.product['_id']), str(duplicate['_id'])})
                self.assertEqual({item['presentation'] for item in conflict['conflicts']}, {'KG', 'KILOGRAMO'})
                self.assertTrue(all(item['stock'] == 8 for item in conflict['conflicts']))
                self.assertNotIn(str(self.foreign['_id']), [item['code'] for item in conflict['conflicts']])

    def test_valid_file_can_conflict_with_existing_catalog_and_reports_original_excel_row(self):
        first = {**self.product, '_id': ObjectId(), 'nombre': 'DEFFOL', 'unidadDeMedida': '4 LT', 'cantidadEnStock': 10}
        second = {**first, '_id': ObjectId(), 'unidadDeMedida': '4 LITROS', 'cantidadEnStock': 5}
        for product in (first, second):
            self.db.productsDb.insert_one(product)
        rows = [{} for _ in range(62)] + [self.row(CODIGO='', PRODUCTO='DEFFOL', PRESENTACION='4 LT', CANTIDAD=37)]
        self.assertTrue(prepare_import(excel(rows), 1, [])['valid'])
        errors = self.assert_rejected_without_writes(rows)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['row'], 64)
        self.assertIn('DEFFOL / 4 LT', errors[0]['message'])
        self.assertEqual({item['stock'] for item in errors[0]['conflicts']}, {10, 5})

    def test_empty_file_missing_or_duplicate_headers_do_not_clear_inventory(self):
        self.assert_rejected_without_writes([])
        self.assert_rejected_without_writes([self.row()], headers=[c for c in EXCEL_COLUMNS if c != 'CANTIDAD'])
        self.assert_rejected_without_writes([self.row()], headers=[*EXCEL_COLUMNS, 'PRODUCTO'])

    def test_real_excel_date_header_has_a_clear_quantity_error(self):
        headers = [datetime(2026, 11, 4), *EXCEL_COLUMNS[2:]]
        errors = self.assert_rejected_without_writes([self.row()], headers=headers)
        self.assertTrue(any(e['row'] == 1 and e['column'] == 'CANTIDAD' for e in errors))

    def test_import_preserves_ids_creation_metadata_and_zeros_only_omitted_local_products(self):
        payload = excel([self.row(), self.row(CODIGO='', PRODUCTO='Azúcar', PRESENTACION='Bolsa')])
        result = complete(products.upload_excel(payload, 1))
        self.assertEqual((result['inserted_count'], result['updated_count'], result['zeroed_count']), (1, 1, 1))
        current = self.db.productsDb.find_one({'_id': self.product['_id']})
        self.assertEqual(current['cantidadEnStock'], 12)
        self.assertEqual(current['fechaDeCreacion'], self.product['fechaDeCreacion'])
        self.assertEqual(current['proveedorId'], 'proveedor')
        self.assertEqual((current['marca'], current['descripcion'], current['categoria']), ('', '', ''))
        self.assertEqual(self.db.productsDb.find_one({'_id': self.absent['_id']})['cantidadEnStock'], 0)
        self.assertEqual(self.db.productsDb.find_one({'_id': self.foreign['_id']}), self.foreign)
        self.assertEqual(self.db.productsDb.count_documents({'local': 1}), 3)
        self.assertEqual(self.db.productHistoryDb.count_documents({}), 0)

    def test_legacy_excel_without_codes_matches_existing_and_repeat_does_not_duplicate(self):
        headers = [c for c in EXCEL_COLUMNS if c != 'CODIGO']
        payload = excel([self.row()], headers)
        for _ in range(2):
            result = complete(products.upload_excel(payload, 1))
            self.assertEqual((result['inserted_count'], result['updated_count']), (0, 1))
        self.assertEqual(self.db.productsDb.count_documents({'local': 1}), 2)
        self.assertIsNotNone(self.db.productsDb.find_one({'_id': self.product['_id']}))

    def test_inventory_changes_after_preview_require_revalidation(self):
        payload = excel([self.row()])
        preview = complete(products.preview_excel(payload, 1))
        self.db.productsDb.update_one({'_id': self.product['_id']}, {'$set': {'cantidadEnStock': 7}})
        original = deepcopy(self.db.productsDb.documents)
        with self.assertRaises(HTTPException) as failure:
            complete(products.upload_excel(payload, 1, preview['catalog_version']))
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(self.db.productsDb.documents, original)
        self.assertEqual(self.db.productImportsDb.count_documents({}), 0)

    def test_success_records_server_utc_date_filename_local_and_counts(self):
        instant = datetime(2026, 11, 5, 0, 30, tzinfo=timezone.utc)
        with patch.object(products, 'datetime') as clock:
            clock.now.return_value = instant
            result = complete(products.upload_excel(excel([self.row()]), 1,
                              filename=r'C:\fakepath\INV. Noviembre 2026.xlsx'))
            clock.now.assert_called_once_with(timezone.utc)
        record = self.db.productImportsDb.find_one({'local': 1})
        self.assertIsInstance(record['imported_at'], datetime)
        self.assertEqual(record['imported_at'], instant)
        self.assertEqual(record['filename'], 'INV. Noviembre 2026.xlsx')
        self.assertEqual({key: record[key] for key in result}, result)
        self.assertEqual(self.db.productImportsDb.count_documents({}), 1)
        public = complete(products.latest_product_import(1))
        self.assertEqual(public['id'], str(record['_id']))
        self.assertEqual(public['imported_at'], '2026-11-05T00:30:00Z')

    def test_failed_inventory_write_does_not_create_a_successful_import_record(self):
        with patch.object(self.db.productsDb, 'update_one', side_effect=RuntimeError('isolated failure')):
            with self.assertRaises(RuntimeError):
                complete(products.upload_excel(excel([self.row()]), 1, filename='fallo.xlsx'))
        self.assertEqual(self.db.productImportsDb.count_documents({}), 0)

    def test_latest_import_is_scoped_to_local_and_has_stable_date_order(self):
        base = {'local': 1, 'filename': 'anterior.xlsx', 'inserted_count': 0,
                'updated_count': 1, 'zeroed_count': 1, 'total_processed': 1}
        old = {**base, '_id': ObjectId('000000000000000000000001'),
               'imported_at': datetime(2026, 11, 1, tzinfo=timezone.utc)}
        recent = {**base, '_id': ObjectId('000000000000000000000002'), 'filename': 'reciente.xlsx',
                  'imported_at': datetime(2026, 11, 5, tzinfo=timezone.utc)}
        tied = {**recent, '_id': ObjectId('000000000000000000000003'), 'filename': 'ultima.xlsx'}
        foreign = {**recent, '_id': ObjectId(), 'local': 2, 'filename': 'otro-local.xlsx',
                   'imported_at': datetime(2026, 12, 1, tzinfo=timezone.utc)}
        for record in (foreign, tied, old, recent):
            self.db.productImportsDb.insert_one(record)
        self.assertEqual(complete(products.latest_product_import(1))['filename'], 'ultima.xlsx')
        self.assertEqual(complete(products.latest_product_import(2))['filename'], 'otro-local.xlsx')
        self.assertIsNone(complete(products.latest_product_import(3)))

    def test_mongo_naive_utc_date_is_serialized_with_explicit_utc(self):
        self.db.productImportsDb.insert_one({
            '_id': ObjectId(), 'local': 1, 'filename': 'conteo.xlsx',
            'imported_at': datetime(2026, 11, 5, 0, 30),
            'inserted_count': 0, 'updated_count': 1, 'zeroed_count': 1, 'total_processed': 1,
        })
        self.assertEqual(complete(products.latest_product_import(1))['imported_at'], '2026-11-05T00:30:00Z')

    def test_rejected_import_preserves_the_previous_successful_import(self):
        complete(products.upload_excel(excel([self.row()]), 1, filename='correcto.xlsx'))
        self.assert_rejected_without_writes([self.row(**{'P. VENTA': None})])
        self.assertEqual(complete(products.latest_product_import(1))['filename'], 'correcto.xlsx')

    def test_latest_import_api_returns_null_or_persisted_info_and_rejects_invalid_local(self):
        async def request(local):
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            async def send(message):
                messages.append(message)
            path = '/api/products/imports/latest'
            scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'GET',
                     'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'root_path': '',
                     'query_string': f'local={local}'.encode(), 'headers': [],
                     'client': ('127.0.0.1', 12345), 'server': ('test', 80)}
            await self.api(scope, receive, send)
            return next(m['status'] for m in messages if m['type'] == 'http.response.start'), json.loads(
                b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))
        self.assertEqual(complete(request(1)), (200, {'data': None}))
        complete(products.upload_excel(excel([self.row()]), 1, filename='guardado.xlsx'))
        status, body = complete(request(1))
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['filename'], 'guardado.xlsx')
        self.assertTrue(body['data']['imported_at'].endswith('Z'))
        self.assertEqual(complete(request(2)), (200, {'data': None}))
        self.assertEqual(complete(request(0))[0], 422)
        self.assertEqual(complete(request('abc'))[0], 422)

    def test_upload_route_records_the_actual_uploaded_filename(self):
        from fastapi import UploadFile
        stream = SpooledTemporaryFile(max_size=1024 * 1024)
        self.addCleanup(stream.close)
        stream.write(excel([self.row()]))
        stream.seek(0)
        file = UploadFile(filename='desde-ruta.xlsx', file=stream)
        result = complete(products_route.upload_products_excel(file=file, local=1, catalog_version=None))
        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(complete(products.latest_product_import(1))['filename'], 'desde-ruta.xlsx')

    def test_http_validation_returns_422_instead_of_fake_success_and_preview_does_not_write(self):
        async def request(path):
            payload = excel([self.row(**{'P. VENTA': None})])
            boundary = 'product-excel-test'
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="local"\r\n\r\n1\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="test.xlsx"\r\n'
                    'Content-Type: application/octet-stream\r\n\r\n').encode() + payload + f'\r\n--{boundary}--\r\n'.encode()
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': body, 'more_body': False}
            async def send(message):
                messages.append(message)
            scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST',
                     'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'root_path': '', 'query_string': b'',
                     'headers': [(b'content-type', f'multipart/form-data; boundary={boundary}'.encode())],
                     'client': ('127.0.0.1', 12345), 'server': ('test', 80)}
            await self.api(scope, receive, send)
            return next(m['status'] for m in messages if m['type'] == 'http.response.start'), json.loads(
                b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))
        original = deepcopy(self.db.productsDb.documents)
        status, body = complete(request('/api/products/preview-excel'))
        self.assertEqual(status, 200)
        self.assertFalse(body['valid'])
        self.assertEqual(body['errors'][0]['column'], 'P. VENTA')
        status, body = complete(request('/api/products/upload-excel'))
        self.assertEqual(status, 422)
        self.assertEqual(body['detail']['errors'][0]['row'], 2)
        self.assertEqual(self.db.productsDb.documents, original)
