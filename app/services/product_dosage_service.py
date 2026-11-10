"""Dosificaciones del producto: edición independiente de stock, precios e importaciones."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.mongo import productsDb
from app.models.product_dosage_model import ProductDosageUpdate
from app.utils.cash_helpers import object_id, serialize


def _query(product_id, user):
    return {'_id': object_id(product_id, 'producto'), 'local': user['local']}


def _response(product, user):
    return serialize({
        'producto': {key: product.get(key) for key in ('_id', 'nombre', 'unidadDeMedida')},
        'dosificaciones': product.get('dosificaciones', []),
        'version': product.get('dosificacionesVersion', 0),
        'puedeEditar': user.get('permissions') == 1,
        'actualizadoEn': product.get('dosificacionesActualizadasEn'),
        'actualizadoPor': product.get('dosificacionesActualizadasPor'),
    })


def retrieve_dosages(product_id, user):
    product = productsDb.find_one(_query(product_id, user))
    if product is None:
        raise HTTPException(404, 'Producto no encontrado en tu local.')
    return _response(product, user)


def save_dosages(product_id, data: ProductDosageUpdate, user):
    if user.get('permissions') != 1:
        raise HTTPException(403, 'No tienes permiso para modificar dosificaciones.')
    query = _query(product_id, user)
    product = productsDb.find_one(query)
    if product is None:
        raise HTTPException(404, 'Producto no encontrado en tu local.')
    if product.get('dosificacionesVersion', 0) != data.version:
        raise HTTPException(409, 'La dosificación cambió desde que la abriste. Recarga los datos antes de guardar.')
    values = {
        'dosificaciones': [entry.model_dump() for entry in data.dosificaciones],
        'dosificacionesVersion': data.version + 1,
        'dosificacionesActualizadasEn': datetime.now(timezone.utc),
        'dosificacionesActualizadasPor': {'_id': user['_id'], 'nombre': user['username']},
    }
    # Una actualización condicional evita sobrescribir cambios de otra persona.
    if data.version == 0:
        query['$or'] = [{'dosificacionesVersion': 0}, {'dosificacionesVersion': {'$exists': False}}]
    else:
        query['dosificacionesVersion'] = data.version
    result = productsDb.update_one(query, {'$set': values})
    if not result.matched_count:
        if productsDb.find_one(_query(product_id, user)) is None:
            raise HTTPException(404, 'Producto no encontrado en tu local.')
        raise HTTPException(409, 'La dosificación cambió desde que la abriste. Recarga los datos antes de guardar.')
    return _response({**product, **values}, user)
