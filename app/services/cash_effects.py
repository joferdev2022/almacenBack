"""Integración de cobros y pagos de todos los medios con Caja."""
from bson.decimal128 import Decimal128
from fastapi import HTTPException

from app.models.payment_model import is_cash, normalize_payment
from app.services import cash_service as cash
from app.utils.cash_helpers import ZERO, money


def capture_payment(user, session, source_type, source_id, event_id, amount, method, description):
    """Registra un cobro o pago nuevo dentro de la jornada abierta."""
    amount = money(amount)
    payment_method = normalize_payment(method)
    if not amount:
        return {"controlado": True, "jornadaId": None, "monto": Decimal128(ZERO),
                "montoOperacion": Decimal128(ZERO), "metodoPago": payment_method,
                "afectaEfectivo": False, "movimientoId": None}
    if payment_method is None:
        raise HTTPException(422, "El método de pago es obligatorio.")
    register = cash.touch_register(user, session)
    journal = cash.lock_open_journal(register, user, session)
    affects_cash = is_cash(payment_method)
    movement = cash.append_movement(journal, user, session, event_id=event_id,
        kind=("VENTA_EFECTIVO" if source_type == "VENTA" else "GASTO_EFECTIVO") if affects_cash
             else ("VENTA_NO_EFECTIVO" if source_type == "VENTA" else "GASTO_NO_EFECTIVO"),
        direction="INGRESO" if amount > ZERO else "EGRESO", amount=abs(amount),
        description=description, source_type=source_type, source_id=source_id,
        payment_method=payment_method)
    return {"controlado": True, "jornadaId": journal["_id"],
            # monto conserva compatibilidad con el impacto físico anterior.
            "monto": Decimal128(amount if affects_cash else ZERO),
            "montoOperacion": Decimal128(amount), "metodoPago": payment_method,
            "afectaEfectivo": affects_cash, "movimientoId": movement["_id"]}


def _legacy_revision(link, target, target_method, user, session, source_type, source_id,
                     event_id, reason, annul):
    """Mantiene sin carga retroactiva los enlaces creados antes del control digital."""
    previous = money(link.get("monto", 0))
    target_cash = target if target_method and is_cash(target_method) else ZERO
    delta = target_cash - previous
    if not delta:
        return link, None
    register = cash.touch_register(user, session)
    original = cash.cashJournalsDb.find_one(
        {"_id": link.get("jornadaId"), "local": user["local"]}, session=session) if link.get("jornadaId") else None
    audit = {"anterior": Decimal128(previous), "nuevo": Decimal128(target_cash),
             "jornadaId": link.get("jornadaId"), "sinMovimiento": False,
             "nota": "Movimiento previo al control digital; solo se ajustó su efecto en efectivo."}
    if not annul and (original is None or original["estado"] == "CERRADA"):
        audit["sinMovimiento"] = True
        audit["nota"] = "Corrección documental posterior: no altera el cierre ni mueve efectivo actual."
    else:
        journal = cash.lock_open_journal(register, user, session, None if annul else original["_id"])
        movement = cash.append_movement(journal, user, session, event_id=event_id,
            kind="AJUSTE_ENTRADA" if delta > ZERO else "AJUSTE_SALIDA",
            direction="INGRESO" if delta > ZERO else "EGRESO", amount=abs(delta),
            description=reason, source_type=source_type, source_id=source_id,
            payment_method="EFECTIVO", movimientoOriginalId=link.get("movimientoId"),
            jornadaOriginalId=link.get("jornadaId"))
        audit["movimientoId"] = movement["_id"]
    link["monto"] = Decimal128(target_cash)
    return link, audit


def _adjustment(journal, link, signed_amount, method, user, session, source_type,
                source_id, event_id, reason, suffix):
    if not signed_amount:
        return None
    return cash.append_movement(journal, user, session, event_id=f"{event_id}:{suffix}",
        kind="AJUSTE_ENTRADA" if signed_amount > ZERO else "AJUSTE_SALIDA",
        direction="INGRESO" if signed_amount > ZERO else "EGRESO", amount=abs(signed_amount),
        description=reason, source_type=source_type, source_id=source_id,
        payment_method=method, movimientoOriginalId=link.get("movimientoId"),
        jornadaOriginalId=link.get("jornadaId"))


def revise_payment(link, target, user, session, source_type, source_id, event_id, reason,
                   annul=False, target_method=None):
    """Corrige importes/métodos con movimientos inmutables y respeta cierres previos."""
    link = dict(link or {})
    if not link.get("controlado"):
        return link, None
    target = money(target)
    normalized_target = normalize_payment(target_method) if target else None
    if target and normalized_target is None:
        raise HTTPException(422, "El método de pago es obligatorio.")
    if "montoOperacion" not in link or not link.get("metodoPago"):
        return _legacy_revision(link, target, normalized_target, user, session, source_type,
            source_id, event_id, reason, annul)

    previous = money(link["montoOperacion"])
    previous_method = normalize_payment(link["metodoPago"])
    if previous == target and previous_method == normalized_target:
        return link, None
    register = cash.touch_register(user, session)
    original = cash.cashJournalsDb.find_one(
        {"_id": link.get("jornadaId"), "local": user["local"]}, session=session) if link.get("jornadaId") else None
    audit = {"anterior": Decimal128(previous), "nuevo": Decimal128(target),
             "metodoAnterior": previous_method, "metodoNuevo": normalized_target,
             "jornadaId": link.get("jornadaId"), "sinMovimiento": False}
    movements = []
    if not annul and (original is None or original["estado"] == "CERRADA"):
        audit["sinMovimiento"] = True
        audit["nota"] = "Corrección documental posterior: no altera el cierre ni los medios de pago de la jornada."
    else:
        journal = cash.lock_open_journal(register, user, session, None if annul else original["_id"])
        if previous_method == normalized_target:
            movement = _adjustment(journal, link, target - previous, previous_method, user, session,
                source_type, source_id, event_id, reason, "DIFERENCIA")
            if movement:
                movements.append(movement)
        else:
            movement = _adjustment(journal, link, -previous, previous_method, user, session,
                source_type, source_id, event_id, reason + " (reverso)", "REVERSO")
            if movement:
                movements.append(movement)
            movement = _adjustment(journal, link, target, normalized_target, user, session,
                source_type, source_id, event_id, reason + " (nuevo método)", "NUEVO") if target else None
            if movement:
                movements.append(movement)
        audit["movimientosIds"] = [movement["_id"] for movement in movements]

    affects_cash = bool(target and is_cash(normalized_target))
    link.update(monto=Decimal128(target if affects_cash else ZERO),
                montoOperacion=Decimal128(target), metodoPago=normalized_target,
                afectaEfectivo=affects_cash,
                movimientoId=movements[-1]["_id"] if movements and target else None)
    return link, audit
