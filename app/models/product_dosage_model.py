from pydantic import BaseModel, ConfigDict, Field


class ProductDosageEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    cultivo: str = Field(min_length=1, max_length=150)
    objetivo: str = Field(default='', max_length=250)
    dosis: str = Field(min_length=1, max_length=250)
    baseAplicacion: str = Field(min_length=1, max_length=200)
    aplicacion: str = Field(default='', max_length=500)
    observaciones: str = Field(default='', max_length=2000)
    fuente: str = Field(default='', max_length=500)


class ProductDosageUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0, strict=True)
    dosificaciones: list[ProductDosageEntry] = Field(max_length=50)
