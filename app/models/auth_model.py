from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId

class UserModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    username: str
    password: str
    local: int

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
        }
      

def ResponseAuthModel(data, message):
    
    return {
            "data": data,
            "code": 200,
            "message": message,
        }


def ErrorResponseModel(error, code, message):
    return {"error": error, "code": code, "message": message}