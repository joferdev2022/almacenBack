from bson import ObjectId
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel

from typing import List
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.services.supplier_service import add_provider, delete_provider_by_id, retrieve_providers, update_provider_by_id, update_provider_debt
from app.models.provider_model import providerModel, ResponseProviderModel, ErrorResponseModel


class ProviderDebtUpdate(BaseModel):
    deuda: float
    monto: float

router = APIRouter()

@router.get("/providers", tags=["providers"])
async def get_providers(page: int = 1, xpage: int = 10, local: int = 1):
    
    
    
    providers_list = await retrieve_providers(page, xpage, local)
    
    # print(products_list)
    return ResponseProviderModel(providers_list, "Lista de proveedores")

@router.post("/providers", tags=["providers"])
async def save_provider(provider_data: providerModel):
    
    new_provider = jsonable_encoder(provider_data)
    print('este es el new provider')
    print(new_provider)
    provider_bd = await add_provider(new_provider)
    print(provider_bd)
    return "ok"

@router.put("/providers/{id}", tags=["providers"])
async def update_provider(id: str, provider_data: providerModel):
    
    provider_update = jsonable_encoder(provider_data)
    result = await update_provider_by_id(id, provider_update)
    
    if result:
        return ResponseProviderModel("Provedor ID: {} actualizado".format(id), "Proveedor actualizado de forma correcta")
        
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla actualizando los datos del Producto",
    )
    
@router.put("/providers/{id}/debt", tags=["providers"])
async def update_provider_debt_route(id: str, body: ProviderDebtUpdate):
    result = await update_provider_debt(id, body.deuda, body.monto)
    if result:
        return ResponseProviderModel(
            f"Deuda actualizada para proveedor ID: {id}", 
            "Deuda actualizada correctamente")
    
@router.delete("/providers/{id}", tags=["providers"])
async def delete_seller(id: str):
    result = await delete_provider_by_id(id)
    if result:
        # return ResponseCustomerModel("Cliente ID: {} borrado".format(id), "Cliente borrado exitosamente")
        return "Proveedor borrado"
    # user = create_user(user_data)
    return ErrorResponseModel(
        "Ocurrió un error",
        404,
        "Hubo una falla borrando los datos del proveedor",
    )