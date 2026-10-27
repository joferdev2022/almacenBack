"""Historial inmutable de productos: deltas pequeños, sin caducidad ni snapshots completos."""
import re
import threading
import time
from datetime import datetime, timezone

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.db.mongo import productsDb, productHistoryDb
from app.services.expenses_service import get_expense_user
from app.utils.cash_helpers import object_id, serialize
from config import settings

FIELDS = ('nombre', 'descripcion', 'categoria', 'precioCompra', 'precioVenta',
          'cantidadEnStock', 'unidadDeMedida', 'proveedorId', 'fechaDeCaducidad', 'local')
optional_login = OAuth2PasswordBearer(tokenUrl='/api/auth', auto_error=False)
_attempts = {}
_attempt_lock = threading.Lock()


def ensure_indexes():
    productHistoryDb.create_index(
        [('local', 1), ('productoId', 1), ('fecha', -1), ('_id', -1)],
        name='product_history_recent')


def optional_product_actor(token: str | None = Depends(optional_login)):
    # Las rutas antiguas siguen aceptando las mismas solicitudes. Nunca se toma
    # la identidad de un campo que el cliente pueda inventar.
    if token:
        try:
            return get_expense_user(token)
        except HTTPException:
            pass
    return None


def record_change(before, after, action, user, session, *, source_id=None, reason=None):
    changes = [{'campo': field, 'antes': before.get(field), 'despues': after.get(field)}
               for field in FIELDS if before.get(field) != after.get(field)]
    if not changes and action != 'ELIMINACION':
        return
    product = after or before
    event = {'productoId': product['_id'], 'local': product.get('local', 0),
             'productoNombre': product.get('nombre', ''), 'accion': action,
             'fecha': datetime.now(timezone.utc), 'cambios': changes,
             'usuarioId': user['_id'] if user else None,
             'usuarioNombre': user.get('username', 'Sin usuario identificado') if user else 'Sin usuario identificado'}
    if source_id is not None:
        event['ventaId'] = source_id
    if reason:
        event['motivo'] = reason
    productHistoryDb.insert_one(event, session=session)


def _check_pin(pin, user):
    encoded = settings.PRODUCT_HISTORY_PIN_HASH
    if not encoded:
        raise HTTPException(503, 'El PIN del historial todavía no está configurado en el servidor.')
    key, now = str(user['_id']), time.monotonic()
    # Cinco intentos por usuario en cinco minutos, también entre distintos productos.
    # Este límite es por proceso; compartirlo en un almacén común al usar varios workers.
    with _attempt_lock:
        for expired in [k for k, (_, until) in _attempts.items() if until <= now]:
            del _attempts[expired]
        count, until = _attempts.get(key, (0, now + 300))
        if count >= 5:
            raise HTTPException(429, 'Demasiados intentos. Espera cinco minutos e inténtalo nuevamente.')
        _attempts[key] = (count + 1, until)
    try:
        valid = bool(re.fullmatch(r'[0-9]{4}', pin)) and bcrypt.checkpw(pin.encode(), encoded.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'La configuración del PIN del historial no es válida.')
    if not valid:
        raise HTTPException(403, 'PIN incorrecto. Inténtalo de nuevo.')
    with _attempt_lock:
        _attempts.pop(key, None)


def retrieve_history(product_id, pin, user):
    _check_pin(pin, user)
    query = {'_id': object_id(product_id, 'producto'), 'local': user['local']}
    product = productsDb.find_one(query)
    if product is None:
        raise HTTPException(404, 'Producto no encontrado.')
    scope = {'productoId': product['_id'], 'local': user['local']}
    rows = productHistoryDb.find(scope).sort([('fecha', -1), ('_id', -1)]).limit(3)
    return serialize({'producto': {k: product.get(k) for k in
                     ('_id', 'nombre', 'unidadDeMedida', 'cantidadEnStock')},
                     'eventos': list(rows), 'total': productHistoryDb.count_documents(scope)})
