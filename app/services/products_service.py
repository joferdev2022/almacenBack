from datetime import datetime, timezone
from bson.objectid import ObjectId
from fastapi import HTTPException
import pandas as pd
from io import BytesIO

from app.db.mongo import productsDb, productImportsDb
from ..utils.helpers import product_helper
from app.services.cash_service import transaction
from app.services.product_history_service import record_change


async def retrieve_products(page: int, xpage: int, local:int):
    
    # productsDb.update_many( {}, { "$set": { "local": 1 } } )
    
    products = []
    totalProducts = productsDb.count_documents({"local": local})
    
    if page < 1 or xpage < 1 or (page - 1) * xpage >= totalProducts:
        raise HTTPException(status_code=400, 
                            detail="Parámetros de paginación inválidos.")
    skipProducts = (page - 1) * xpage
    
    for product in productsDb.find({"local": local}).skip(skipProducts).limit(xpage):
        product["id"] = str(product["_id"])
        products.append(product_helper(product))
    return {"total": totalProducts, "products": products, "page": page, "xpage": xpage}

async def add_product(product_data: dict, user=None) -> dict:
    product_data["_id"] = ObjectId()
    def write(session):
        product = productsDb.insert_one(product_data, session=session)
        new_product = productsDb.find_one({"_id": product.inserted_id}, session=session)
        record_change({}, new_product, 'CREACION', user, session)
        return product_helper(new_product)
    return transaction(write)

async def update_product_by_id(producto_id: str, new_data: dict, user=None):
    if "_id" in new_data:
        del new_data["_id"]
    def write(session):
        producto = productsDb.find_one({"_id": ObjectId(producto_id)}, session=session)
        if not producto:
            return False
        productsDb.update_one(
            {"_id": ObjectId(producto_id)}, {"$set": new_data}, session=session
        )
        record_change(producto, {**producto, **new_data}, 'EDICION_MANUAL', user, session)
        return True
    return transaction(write)

async def delete_product_by_id(product_id: str, user=None):
    filter = {"_id": ObjectId(product_id)}
    
    def write(session):
        before = productsDb.find_one(filter, session=session)
        result = productsDb.delete_one(filter, session=session)
        if result.deleted_count == 1:
            record_change(before, {}, 'ELIMINACION', user, session)
            return True
        return False
    return transaction(write)


def _prepare_excel(file_data: bytes, local: int):
    from app.services.product_excel_service import prepare_import
    if local < 1:
        raise HTTPException(422, 'Selecciona un local válido.')
    return prepare_import(file_data, local, list(productsDb.find({'local': local})))


async def preview_excel(file_data: bytes, local: int):
    from app.services.product_excel_service import public_plan
    return public_plan(_prepare_excel(file_data, local))


async def upload_excel(file_data: bytes, local: int, expected_version: str | None = None,
                       filename: str | None = None):
    plan = _prepare_excel(file_data, local)
    if not plan['valid']:
        raise HTTPException(422, detail={
            'message': 'Corrige los errores del Excel. No se modificó ningún producto.',
            'errors': plan['errors'],
        })
    if expected_version is not None and expected_version != plan['catalog_version']:
        raise HTTPException(409, 'El inventario cambió desde la validación. Valida el archivo nuevamente.')

    # Solo se escribe después de validar todas las filas y coincidencias.
    # Se conservan los IDs y los productos ausentes permanecen con stock cero.
    for product_id, values in plan['_updates']:
        productsDb.update_one({'_id': product_id, 'local': local}, {'$set': values})
    for values in plan['_new']:
        productsDb.insert_one({**values, '_id': ObjectId(), 'proveedorId': None,
                               'fechaDeCaducidad': None, 'fechaDeCreacion': datetime.now()})
    for product_id in plan['_zero']:
        productsDb.update_one({'_id': product_id, 'local': local}, {'$set': {'cantidadEnStock': 0}})
    result = {key: plan[key] for key in ('inserted_count', 'updated_count', 'zeroed_count', 'total_processed')}
    productImportsDb.insert_one({
        '_id': ObjectId(), 'local': local,
        'imported_at': datetime.now(timezone.utc),
        'filename': (filename or '').replace('\\', '/').rsplit('/', 1)[-1].strip() or 'productos.xlsx',
        **result,
    })
    return result


async def latest_product_import(local: int):
    if local < 1:
        raise HTTPException(422, 'Selecciona un local válido.')
    record = productImportsDb.find_one({'local': local}, sort=[('imported_at', -1), ('_id', -1)])
    if record is None:
        return None
    imported_at = record['imported_at']
    # MongoDB devuelve UTC sin tzinfo cuando el cliente usa su configuración predeterminada.
    if imported_at.tzinfo is None:
        imported_at = imported_at.replace(tzinfo=timezone.utc)
    return {
        'id': str(record['_id']), 'local': record['local'], 'filename': record['filename'],
        'imported_at': imported_at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
        **{key: record[key] for key in ('inserted_count', 'updated_count', 'zeroed_count', 'total_processed')},
    }


async def download_excel(local: int):
    
    productos = list(productsDb.find({"local": local}))
    
    if not productos:
        raise HTTPException(status_code=404, detail="No hay productos para descargar")
    
    datos = []
    
    for prod in productos:
        datos.append({
            "CODIGO": str(prod["_id"]),
            "CANTIDAD": prod.get("cantidadEnStock", 0),
            "PRODUCTO": prod.get("nombre", ""),
            "PRESENTACION": prod.get("unidadDeMedida", ""),
            "MARCA": prod.get("marca", ""),
            "CATEGORIA": prod.get("categoria", ""),
            "DESCRIPCION": prod.get("descripcion", ""),
            "P. UNITARIO": prod.get("precioCompra", 0),
            "P. VENTA": prod.get("precioVenta", 0),
         })
    
    
    df = pd.DataFrame(datos)
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Productos', index=False)
    
    output.seek(0)
    
    
    return {
        "file": output.getvalue(),
        "filename": f"productos_local_{local}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    }
