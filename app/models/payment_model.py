"""Catálogo compartido de medios de pago de almacen."""
from typing import Literal, get_args
from fastapi import HTTPException

PaymentMethod = Literal["EFECTIVO", "YAPE", "PLIN", "TRANSFERENCIA", "TARJETA", "OTRO"]


def normalize_payment(value):
    if value is None or value == "":
        return None
    normalized = str(value).strip().upper()
    if normalized not in get_args(PaymentMethod):
        raise ValueError("Método de pago no válido.")
    return normalized


def is_cash(value):
    return normalize_payment(value) == "EFECTIVO"
