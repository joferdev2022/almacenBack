from datetime import datetime
from bson.objectid import ObjectId
from fastapi import HTTPException
import pandas as pd
from io import BytesIO

from app.db.mongo import productsDb
from ..utils.helpers import product_helper


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

async def add_product(product_data: dict) -> dict:
    product_data["_id"] = ObjectId()
    product =  productsDb.insert_one(product_data)
    new_product =  productsDb.find_one({"_id": product.inserted_id})
    
    return product_helper(new_product)

async def update_product_by_id(producto_id: str, new_data: dict):
    if "_id" in new_data:
        del new_data["_id"]
    producto = productsDb.find_one({"_id": ObjectId(producto_id)})
    # print("esta imprimiendo el product")
    # print(producto)
    if producto:
        productsDb.update_one(
            {"_id": ObjectId(producto_id)}, {"$set": new_data}
        )
        return True
    return False

async def delete_product_by_id(product_id: str):
    filter = {"_id": ObjectId(product_id)}
    
    result =  productsDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False


# async def upload_excel(file_data: bytes, local: int):
    

#     df = pd.read_excel(BytesIO(file_data))
#     records = df.to_dict(orient='records')
    
#     for record in records:
#         record["local"] = local
#         record["_id"] = ObjectId()
    
#     if records:
#         productsDb.insert_many(records)
    
#     return {"inserted_count": len(records)}


async def upload_excel(file_data: bytes, local: int):
    df = pd.read_excel(BytesIO(file_data))
    
    df.columns = [col.strip().upper() for col in df.columns]
    df = df.where(pd.notna(df), None)
    
    records = df.to_dict(orient='records')
    
    # Funciones helper para convertir valores de forma segura
    def safe_float(value):
        if value is None or pd.isna(value):
            return 0
        try:
            result = float(value)
            return result if not pd.isna(result) else 0
        except (ValueError, TypeError):
            return 0
    
    def safe_int(value):
        if value is None or pd.isna(value):
            return 0
        try:
            result = int(float(value))
            return result if not pd.isna(result) else 0
        except (ValueError, TypeError):
            return 0
    
    def safe_string(value):
        if value is None or pd.isna(value):
            return ""
        return str(value).strip()
    
    # Mapear todos los registros del Excel al modelo
    mapped_records = []
    for record in records:
        # Limpiar claves del registro
        record = {k.strip().upper() if isinstance(k, str) else k: v for k, v in record.items()}

        nombre = str(record.get("PRODUCTO", "")).strip() if record.get("PRODUCTO") else ""
        presentacion = str(record.get("PRESENTACION", "")).strip() if record.get("PRESENTACION") else ""
        
        # Saltar filas vacías
        if not nombre:
            continue
        
        mapped_records.append({
            "_id": ObjectId(),
            "nombre": nombre,
            "descripcion": safe_string(record.get("DESCRIPCION")),
            "categoria": safe_string(record.get("CATEGORIA")),
            "precioCompra": safe_float(record.get("P. UNITARIO")),
            "precioVenta": safe_float(record.get("P. VENTA")),
            "cantidadEnStock": safe_int(record.get("CANTIDAD")),
            "unidadDeMedida": presentacion,
            "marca": safe_string(record.get("MARCA")),
            "proveedorId": record.get("PROVEEDORID") if record.get("PROVEEDORID") and not pd.isna(record.get("PROVEEDORID")) else None,
            "fechaDeCaducidad": record.get("FECHADECADUCIDAD") if record.get("FECHADECADUCIDAD") and not pd.isna(record.get("FECHADECADUCIDAD")) else None,
            "local": local,
            "fechaDeCreacion": datetime.now()
        })
    
    # 1. Eliminar todos los productos del local
    delete_result = productsDb.delete_many({"local": local})
    deleted_count = delete_result.deleted_count
    
    # 2. Insertar todos los productos nuevos de golpe
    inserted_count = 0
    if mapped_records:
        productsDb.insert_many(mapped_records)
        inserted_count = len(mapped_records)
    
    return {
        "deleted_count": deleted_count,
        "inserted_count": inserted_count,
        "total_processed": len(records)
    }


async def download_excel(local: int):
    
    productos = list(productsDb.find({"local": local}))
    
    if not productos:
        raise HTTPException(status_code=404, detail="No hay productos para descargar")
    
    datos = []
    
    for prod in productos:
        datos.append({
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