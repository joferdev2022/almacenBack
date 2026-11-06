"""Validación y vista previa del conteo completo, sin escrituras en la base de datos."""
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook


EXCEL_COLUMNS = ('CODIGO', 'CANTIDAD', 'PRODUCTO', 'PRESENTACION', 'MARCA',
                 'CATEGORIA', 'DESCRIPCION', 'P. UNITARIO', 'P. VENTA')
REQUIRED_COLUMNS = ('CANTIDAD', 'PRODUCTO', 'PRESENTACION', 'P. UNITARIO', 'P. VENTA')


def text(value):
    return '' if value is None else str(value).strip()


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', text(value)).casefold().split())


def presentation_key(value):
    """Reconoce la misma presentación aunque cambien espacios o nombres de unidades."""
    value = normalized(value)
    match = re.fullmatch(r'(\d+(?:[.,]\d+)?)?\s*(l|lt|lts|litros?|ml|mililitros?|kg|kilos?|kilogramos?|g|gr|gramos?)', value)
    if not match:
        return value
    amount = Decimal((match[1] or '1').replace(',', '.'))
    unit = match[2]
    if unit in ('l', 'lt', 'lts', 'litro', 'litros'):
        amount, unit = amount * 1000, 'ml'
    elif unit.startswith('mililitro'):
        unit = 'ml'
    elif unit == 'kg' or unit.startswith('kilo'):
        amount, unit = amount * 1000, 'g'
    elif unit == 'gr' or unit.startswith('gramo'):
        unit = 'g'
    return f'{amount.normalize()}{unit}'


def product_key(name, presentation):
    return normalized(name), presentation_key(presentation)


def catalog_version(catalog):
    content = json.dumps(sorted(catalog, key=lambda item: str(item['_id'])),
                         sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def prepare_import(file_data, local, catalog):
    errors = []
    plan = {'valid': False, 'errors': errors, 'total_processed': 0,
            'inserted_count': 0, 'updated_count': 0, 'zeroed_count': 0,
            'preview': [], 'catalog_version': catalog_version(catalog),
            '_new': [], '_updates': [], '_zero': []}

    def error(row, column, message, conflicts=None):
        item = {'row': row, 'column': column, 'message': message}
        if conflicts:
            item['conflicts'] = [
                {'code': str(product['_id']), 'name': product.get('nombre', ''),
                 'presentation': product.get('unidadDeMedida', ''),
                 'stock': product.get('cantidadEnStock', 0), 'category': product.get('categoria', '')}
                for product in sorted(conflicts, key=lambda product: str(product['_id']))
            ]
        errors.append(item)

    try:
        book = load_workbook(BytesIO(file_data), read_only=True, data_only=False)
    except Exception:
        error(None, 'ARCHIVO', 'No se pudo leer el Excel. Utiliza un archivo .xlsx válido.')
        return plan

    try:
        if 'Productos' in book.sheetnames:
            sheet = book['Productos']
        elif len(book.sheetnames) == 1:
            sheet = book.worksheets[0]
        else:
            error(None, 'ARCHIVO', 'El archivo debe incluir una hoja llamada Productos.')
            return plan

        rows = iter(sheet.iter_rows())
        header = next(rows, ())
        columns = {}
        for index, cell in enumerate(header):
            name = ''.join(char for char in unicodedata.normalize('NFKD', text(cell.value))
                           if not unicodedata.combining(char)).upper()
            if name in EXCEL_COLUMNS:
                if name in columns:
                    error(1, name, f'La columna {name} está repetida.')
                columns[name] = index
        for name in REQUIRED_COLUMNS:
            if name not in columns:
                error(1, name, f'Falta el encabezado {name} en la primera fila.')
        if errors:
            return plan

        catalog_by_id = {str(item['_id']): item for item in catalog}
        catalog_by_key = defaultdict(list)
        for item in catalog:
            catalog_by_key[product_key(item.get('nombre'), item.get('unidadDeMedida'))].append(item)
        file_keys, file_codes = defaultdict(list), defaultdict(list)
        matched_ids = set()

        for row_number, cells in enumerate(rows, start=2):
            raw = {name: cells[index].value if index < len(cells) else None
                   for name, index in columns.items()}
            if all(not text(value) for value in raw.values()):
                continue
            plan['total_processed'] += 1
            row_errors = len(errors)
            invalid_cells = set()
            for name, index in columns.items():
                if index < len(cells) and cells[index].data_type in ('f', 'e'):
                    invalid_cells.add(name)
                    error(row_number, name, 'La celda contiene una fórmula o un error. Escribe su valor.')
            name, presentation = text(raw.get('PRODUCTO')), text(raw.get('PRESENTACION'))
            for column, value in (('PRODUCTO', name), ('PRESENTACION', presentation)):
                if not value:
                    error(row_number, column, 'Este dato es obligatorio y no puede estar vacío.')

            def number(column, integer=False):
                value = raw.get(column)
                if column in invalid_cells:
                    return None
                if not text(value):
                    if integer:
                        return 0
                    error(row_number, column, 'Este precio es obligatorio y no puede estar vacío.')
                    return None
                try:
                    if isinstance(value, bool):
                        raise ValueError()
                    amount = Decimal(text(value))
                    if not amount.is_finite() or amount < 0:
                        raise ValueError()
                    if integer:
                        if amount != amount.to_integral_value() or amount > 2**63 - 1:
                            raise ValueError()
                        return int(amount)
                    result = float(amount)
                    if not math.isfinite(result):
                        raise ValueError()
                    return result
                except (InvalidOperation, ValueError, OverflowError):
                    message = ('Escribe una cantidad entera mayor o igual a cero.' if integer else
                               'Escribe un precio numérico mayor o igual a cero, sin símbolos de moneda.')
                    error(row_number, column, message)
                    return None

            quantity = number('CANTIDAD', integer=True)
            buy, sale = number('P. UNITARIO'), number('P. VENTA')
            code = text(raw.get('CODIGO')).lower()
            key = product_key(name, presentation)
            if name and presentation:
                file_keys[key].append(row_number)
            if code:
                file_codes[code].append(row_number)
            existing = None
            candidates = catalog_by_key.get(key, []) if name and presentation else []
            if code:
                existing = catalog_by_id.get(code)
                if existing is None:
                    error(row_number, 'CODIGO', 'El código no existe en este local. Descarga el Excel actualizado.')
                elif any(item['_id'] != existing['_id'] for item in candidates):
                    error(row_number, 'PRODUCTO / PRESENTACION',
                          f'Ya existe otro producto registrado como «{name} / {presentation}» en este local. Revisa las coincidencias antes de importar.',
                          conflicts=candidates)
            elif len(candidates) > 1:
                error(row_number, 'PRODUCTO / PRESENTACION',
                      f'Hay {len(candidates)} productos registrados como «{name} / {presentation}» en este local. Corrige la duplicidad antes de importar.',
                      conflicts=candidates)
            elif candidates:
                existing = candidates[0]
            if not code and existing:
                file_codes[str(existing['_id'])].append(row_number)

            if len(errors) != row_errors:
                continue
            payload = {'nombre': name, 'unidadDeMedida': presentation,
                       'cantidadEnStock': quantity, 'precioCompra': buy, 'precioVenta': sale,
                       'marca': text(raw.get('MARCA')), 'categoria': text(raw.get('CATEGORIA')),
                       'descripcion': text(raw.get('DESCRIPCION')), 'local': local}
            if existing:
                matched_ids.add(existing['_id'])
                plan['_updates'].append((existing['_id'], payload))
            else:
                plan['_new'].append(payload)
            plan['preview'].append({'row': row_number, 'code': str(existing['_id']) if existing else None,
                                    'name': name, 'presentation': presentation,
                                    'stock_before': existing.get('cantidadEnStock', 0) if existing else None,
                                    'stock_after': quantity, 'action': 'update' if existing else 'create'})

        for column, groups in (('PRODUCTO / PRESENTACION', file_keys), ('CODIGO', file_codes)):
            for positions in groups.values():
                if len(positions) > 1:
                    for position in positions:
                        others = ', '.join(str(row) for row in positions if row != position)
                        error(position, column, f'Duplicado: coincide con la fila {others}. La carga se ha bloqueado.')
        if not plan['total_processed']:
            error(None, 'ARCHIVO', 'El Excel no contiene productos. No se modificará el inventario.')
        if errors:
            plan['preview'] = []
            return plan

        for existing in catalog:
            if existing['_id'] not in matched_ids:
                plan['_zero'].append(existing['_id'])
                plan['preview'].append({'row': None, 'code': str(existing['_id']),
                                        'name': existing.get('nombre', ''),
                                        'presentation': existing.get('unidadDeMedida', ''),
                                        'stock_before': existing.get('cantidadEnStock', 0),
                                        'stock_after': 0, 'action': 'zero'})
        plan.update(valid=True, inserted_count=len(plan['_new']),
                    updated_count=len(plan['_updates']), zeroed_count=len(plan['_zero']))
        return plan
    finally:
        book.close()


def public_plan(plan):
    return {key: value for key, value in plan.items() if not key.startswith('_')}
