"""Idempotencia y auditoría de operaciones de almacen."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.utils.cash_helpers import fingerprint


class OperationReason(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    motivo: str = Field(min_length=3, max_length=500)


def operation_key(value: Annotated[str, Header(alias="Idempotency-Key")]):
    try:
        return str(UUID(value))
    except ValueError as error:
        raise HTTPException(422, "El identificador de operación debe ser un UUID válido.") from error


def operation_hash(action, payload):
    return fingerprint({"accion": action, "datos": payload})


def was_applied(document, key, digest):
    for operation in document.get("operaciones", []):
        if operation["id"] == key:
            if operation["huella"] != digest:
                raise HTTPException(409, "Esta operación ya fue utilizada con otros datos.")
            return True
    return False


def stamp(document, key, digest, user, action, reason=None, changes=None):
    now = datetime.now(timezone.utc)
    document.setdefault("operaciones", []).append({"id": key, "huella": digest})
    document.setdefault("auditoria", []).append({
        "accion": action, "fecha": now, "usuarioId": user["_id"],
        "usuarioNombre": user["username"], "motivo": reason,
        "cambios": changes or [],
    })
    document["updated_at"] = now
    document["updated_by"] = user["_id"]
    document["version"] = document.get("version", 0) + 1


def ensure_active(document):
    if document.get("anulado"):
        raise HTTPException(409, "La operación está anulada y solo se puede consultar.")
