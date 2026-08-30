"""Integración de cobros/pagos con Caja; nunca se llama desde Angular."""
from bson.decimal128 import Decimal128
from fastapi import HTTPException

from app.services import cash_service as cash
from app.utils.cash_helpers import ZERO, money


def capture_payment(user, session, source_type, source_id, event_id, amount, description):
    """Monto firmado: venta positiva, gasto negativo; no efectivo = cero."""
    amount = money(amount)
    register = cash.touch_register(user, session)
    active = register.get("inicioControl") is not None
    link = {"controlado": active, "jornadaId": None, "monto": Decimal128(ZERO), "movimientoId": None}
    if amount:
        # Una escritura nueva en efectivo siempre exige Caja abierta, incluso si
        # las colecciones fueron vaciadas y aún no existe una primera apertura.
        journal = cash.lock_open_journal(register, user, session)
        link["controlado"] = True
    elif not active:
        # Los métodos no efectivos previos a la primera apertura no se importan
        # retroactivamente cuando el control de Caja comience.
        return link
    else:
        journal = cash.cashJournalsDb.find_one(
            {"local": user["local"], "cajaId": register["_id"], "estado": "ABIERTA"}, session=session)
    if journal:
        link["jornadaId"] = journal["_id"]
    if amount:
        movement = cash.append_movement(journal, user, session, event_id=event_id,
            kind="VENTA_EFECTIVO" if source_type == "VENTA" else "GASTO_EFECTIVO",
            direction="INGRESO" if amount > ZERO else "EGRESO", amount=abs(amount),
            description=description, source_type=source_type, source_id=source_id)
        link.update(monto=Decimal128(amount), movimientoId=movement["_id"])
    return link


def revise_payment(link, target, user, session, source_type, source_id, event_id, reason, annul=False):
    """Correcciones cerradas son documentales; anular revierte en la caja actual.

    Una corrección de un cobro inexistente no es una devolución de efectivo.
    Nunca se agrega un movimiento a una jornada cerrada.
    """
    link = dict(link or {})
    if not link.get("controlado"):
        return link, None  # No importar operaciones anteriores a la primera apertura.
    previous, target = money(link.get("monto", 0)), money(target)
    delta = target - previous
    if not delta:
        return link, None
    register = cash.touch_register(user, session)
    original = cash.cashJournalsDb.find_one(
        {"_id": link.get("jornadaId"), "local": user["local"]}, session=session) if link.get("jornadaId") else None
    audit = {"anterior": Decimal128(previous), "nuevo": Decimal128(target),
             "jornadaId": link.get("jornadaId"), "sinMovimiento": False}
    if not annul and (original is None or original["estado"] == "CERRADA"):
        audit["sinMovimiento"] = True
        audit["nota"] = "Corrección documental posterior: no altera el cierre ni mueve efectivo actual."
    else:
        journal = cash.lock_open_journal(register, user, session,
            None if annul else original["_id"])
        movement = cash.append_movement(journal, user, session, event_id=event_id,
            kind="AJUSTE_ENTRADA" if delta > ZERO else "AJUSTE_SALIDA",
            direction="INGRESO" if delta > ZERO else "EGRESO", amount=abs(delta),
            description=reason, source_type=source_type, source_id=source_id,
            movimientoOriginalId=link.get("movimientoId"), jornadaOriginalId=link.get("jornadaId"))
        audit["movimientoId"] = movement["_id"]
    link["monto"] = Decimal128(target)
    return link, audit
