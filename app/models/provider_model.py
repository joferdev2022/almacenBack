from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime

class providerModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    nombreProvider: str
    numeroProvider: Optional[str]=None
    deudaInicial: float = 0.0
    deudaActual: float = 0.0
    estadoProvider: str = "PENDIENTE"
    local: 0
    fechaCreacion: Optional[datetime] = None
    fechaUltimoPago: Optional[datetime] = None
    pagos: Optional[List[Dict[str, Any]]] = []  # <-- Añadido

    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
            
        }
        schema_extra = {
            "example": {
                "nombreProvider": "Jose Perez",
                "numeroProvider": "123456789",
                "deudaInicial": 1000.0,
                "deudaActual": 500.0,
                "estadoProvider": "PENDIENTE",
                "local":0,
                # "fechaDeCaducidad": "",
                # "codigoDeBarras": "1234567890123"
            }
        }
        
def ResponseProviderModel(data, message):
    print('despues de esto viene la data de model')
    print(data)
    
    if "page" in data:
        
        
        
        return {
            "data": [data["providers"]],
            "total":data["total"],
            "page":data["page"],
            "xpage":data["xpage"],
            "code": 200,
            "message": message,
        }
    return {
            "data": data,
            "code": 200,
            "message": message,
        }


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}