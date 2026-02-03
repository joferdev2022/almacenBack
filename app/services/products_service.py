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
    print("esta imprimiendo el product")
    print(producto)
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


async def upload_excel(file_data: bytes, local: int):
    

    df = pd.read_excel(BytesIO(file_data))
    records = df.to_dict(orient='records')
    
    for record in records:
        record["local"] = local
        record["_id"] = ObjectId()
    
    if records:
        productsDb.insert_many(records)
    
    return {"inserted_count": len(records)}


async def upload_excel(file_data: bytes, local: int):
    df = pd.read_excel(BytesIO(file_data))
    
    df.columns = [col.strip().upper() for col in df.columns]

    df = df.where(pd.notna(df), None)
    
    records = df.to_dict(orient='records')
    
    print(records)
    
    inserted_count = 0
    updated_count = 0
    
    
    for record in records:
        # Limpiar claves del registro
        record = {k.strip().upper() if isinstance(k, str) else k: v for k, v in record.items()}

        # Mapear columnas del Excel al modelo
        nombre = str(record.get("PRODUCTO", "")).strip() if record.get("PRODUCTO") else ""
        # Saltar filas vacías
        if not nombre:
            continue
        
        # Función helper para convertir valores de forma segura
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
        
        
        # Debug: imprime los valores leídos
        precio_compra_raw = record.get("P. UNITARIO")
        precio_venta_raw = record.get("P. VENTA")
        
        print(f"Producto: {nombre}")
        print(f"  P.UNITARIO raw: {precio_compra_raw} (tipo: {type(precio_compra_raw)})")
        print(f"  P.VENTA raw: {precio_venta_raw} (tipo: {type(precio_venta_raw)})")
        
        
        # Mapear columnas del Excel al modelo
        mapped_record = {
            "nombre": nombre,
            "descripcion": safe_string(record.get("DESCRIPCION")),
            "categoria": safe_string(record.get("CATEGORIA")),
            "precioCompra": safe_float(record.get("P. UNITARIO")),
            "precioVenta": safe_float(record.get("P. VENTA")),
            "cantidadEnStock": safe_int(record.get("CANTIDAD")),
            "unidadDeMedida": safe_string(record.get("PRESENTACION")) or safe_string(record.get("'PRESENTACION")),
            "marca": safe_string(record.get("MARCA")),
            "proveedorId": record.get("PROVEEDORID") if record.get("PROVEEDORID") and not pd.isna(record.get("PROVEEDORID")) else None,
            "fechaDeCaducidad": record.get("FECHADECADUCIDAD") if record.get("FECHADECADUCIDAD") and not pd.isna(record.get("FECHADECADUCIDAD")) else None,
            "local": local,
            "fechaDeCreacion": datetime.now()
        }
        
        print(f"  precioCompra convertido: {mapped_record['precioCompra']}")
        print(f"  precioVenta convertido: {mapped_record['precioVenta']}")
        
        
        filter_query = {
            "nombre": mapped_record["nombre"],
            "local": local
        }
        
        # Upsert: actualiza si existe, inserta si no
        result = productsDb.update_one(
            filter_query,
            {"$set": mapped_record},
            upsert=True
        )
        
        if result.upserted_id:
            inserted_count += 1
        elif result.modified_count > 0:
            updated_count += 1
    
    
    
    return {
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "total_processed": len(records)
    }