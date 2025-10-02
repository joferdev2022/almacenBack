from bson.objectid import ObjectId
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.mongo import providersDb
from ..utils.helpers import provider_helper

async def retrieve_providers(page: int, xpage: int, local:int):
    providers = []
    totalProviders = providersDb.count_documents({"local": local})
    print(totalProviders)
    
    if page < 1 or xpage < 1 or (page - 1) * xpage >= totalProviders:
        raise HTTPException(status_code=400, detail="Parámetros de paginación inválidos.")
    skipSellers = (page - 1) * xpage
    
    for provider in providersDb.find({"local": local}).skip(skipSellers).limit(xpage):
        provider["id"] = str(provider["_id"])
        # print(seller)
        providers.append(provider_helper(provider))
    return {"total": totalProviders, "providers": providers, "page": page, "xpage": xpage}


async def add_provider(provider_data: dict) -> dict:
    
    print("este es el provider data en service")
    print(provider_data)
    provider_data["_id"] = ObjectId()
    
    provider_data["fechaCreacion"] = datetime.now(timezone.utc)
    
    
    deuda_inicial = float(provider_data.get("deudaInicial", 0.0))
    provider_data["deudaInicial"] = deuda_inicial
    provider_data["deudaActual"] = deuda_inicial
    
    
    provider =  providersDb.insert_one(provider_data)
    new_provider =  providersDb.find_one({"_id": provider.inserted_id})
    print("este es el new provider despues de la bd")
    print(new_provider)
    
    return provider_helper(new_provider)

async def update_provider_by_id(provider_id: str, new_data: dict):
    if "_id" in new_data:
        del new_data["_id"]
    provider = providersDb.find_one({"_id": ObjectId(provider_id)})
    print("esta imprimiendo el provider")
    print(provider)
    if provider:
        providersDb.update_one(
            {"_id": ObjectId(provider_id)}, {"$set": new_data}
        )
        return True
    return False

async def delete_provider_by_id(provider_id: str):
    filter = {"_id": ObjectId(provider_id)}
    
    result =  providersDb.delete_one(filter)
    if result.deleted_count == 1:
        # user_updated =  Items.find_one({"_id": user_id})
        return True
    return False

async def update_provider_debt(provider_id: str, new_debt: float, monto_pago: float):
    now = datetime.now(timezone.utc)
    update_fields = {
        "deudaActual": new_debt,
        "fechaUltimoPago": now # Añade la fecha del último pago
    }
    if new_debt == 0:
        update_fields["estadoProvider"] = "CANCELADO"
    result = providersDb.update_one(
        {"_id": ObjectId(provider_id)},
        {"$set": update_fields,
         "$push": {"pagos": {"fecha": now, "monto": monto_pago}}
         }
    )
    return result.modified_count == 1