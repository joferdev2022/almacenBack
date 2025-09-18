from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from datetime import datetime

class sellerModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    nombreVendedor: str
    aliasVendedor: Optional[str]=None
    local: 0
   
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
            
        }
        schema_extra = {
            "example": {
                "nombreVendedor": "Jose Perez",
                "aliasVendedor": "Vendedor1",
                "local":0,
                # "fechaDeCaducidad": "",
                # "codigoDeBarras": "1234567890123"
            }
        }
        
def ResponseSellerModel(data, message):
    
    if "page" in data:
        
        return {
            "data": [data["sellers"]],
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