"""Caja física de almacen. Movimientos inmutables y escrituras transaccionales."""
from datetime import datetime, timezone

from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.db.mongo import client, cashRegistersDb, cashJournalsDb, cashMovementsDb, salesDb, expensesDb
from app.models.cash_model import CashClosing, CashManualMovement, CashOpening
from app.utils.cash_helpers import ZERO, date_filter, fingerprint, money, object_id, serialize

NO_OPEN_CASH = "No existe una caja abierta para registrar esta operación en efectivo."


def ensure_indexes():
    for collection, expected in ((cashRegistersDb, "cash_registers"),
                                 (cashJournalsDb, "cash_journals"),
                                 (cashMovementsDb, "cash_movements")):
        if collection.full_name != f"almacen.{expected}":
            raise RuntimeError("Caja solo puede utilizar las colecciones de almacen.")
    cashRegistersDb.create_index([("local", 1), ("codigo", 1)], unique=True, name="cash_register_local_code")
    cashJournalsDb.create_index([("cajaId", 1)], unique=True,
        partialFilterExpression={"estado": "ABIERTA"}, name="cash_one_open_journal")
    cashJournalsDb.create_index([("local", 1), ("operacionApertura", 1)], unique=True,
        name="cash_opening_operation")
    cashJournalsDb.create_index([("local", 1), ("fechaApertura", -1), ("_id", -1)], name="cash_journal_history")
    cashMovementsDb.create_index([("local", 1), ("eventoId", 1)], unique=True, name="cash_unique_event")
    cashMovementsDb.create_index([("local", 1), ("jornadaId", 1), ("fecha", -1), ("_id", -1)], name="cash_journal_movements")
    cashMovementsDb.create_index([("local", 1), ("origenTipo", 1), ("origenId", 1)], name="cash_movement_source")
    for collection, name in ((salesDb, "sales"), (expensesDb, "expenses")):
        if collection.full_name != f"almacen.{name}":
            raise RuntimeError("La integración de Caja solo admite almacen.")
        collection.create_index([("local", 1), ("operacionCreacion", 1)], unique=True,
            partialFilterExpression={"operacionCreacion": {"$type": "string"}},
            name=f"{name}_creation_operation")
    salesDb.create_index([("local", 1), ("fechaVenta", -1), ("_id", -1)], name="sales_local_fecha")



def transaction(callback):
    """No degradar a escrituras separadas si Mongo no admite transacciones.
    Reintentar una colisión de creación del registro del local vuelve a consultar
    la operación idempotente; nunca reejecuta solamente una inserción.
    """
    for attempt in range(3):
        try:
            with client.start_session() as session:
                return session.with_transaction(callback,
                    read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority"))
        except DuplicateKeyError as error:
            if attempt == 2:
                raise HTTPException(409, "La operación ya existe o la caja cambió. Actualiza e intenta nuevamente.") from error
        except OperationFailure as error:
            if error.code in (20, 303):
                raise HTTPException(503, "Caja necesita transacciones de MongoDB. No se guardó la operación.") from error
            raise


def _now():
    return datetime.now(timezone.utc)


def touch_register(user, session):
    """Serializa apertura y operaciones del local, incluso antes de activarse."""
    now = _now()
    return cashRegistersDb.find_one_and_update(
        {"local": user["local"], "codigo": "PRINCIPAL"},
        {"$setOnInsert": {"nombre": "Caja principal", "activa": True,
                          "created_at": now, "inicioControl": None},
         "$set": {"updated_at": now}, "$inc": {"version": 1}},
        upsert=True, return_document=ReturnDocument.AFTER, session=session)


def lock_open_journal(register, user, session, journal_id=None, expected_version=None):
    query = {"cajaId": register["_id"], "local": user["local"], "estado": "ABIERTA"}
    if journal_id is not None:
        query["_id"] = object_id(journal_id)
    if expected_version is not None:
        query["version"] = expected_version
    journal = cashJournalsDb.find_one_and_update(query,
        {"$inc": {"version": 1}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER, session=session)
    if journal is None:
        if expected_version is not None:
            raise HTTPException(409, "La caja cambió o ya fue cerrada. Actualiza el resumen antes de cerrar.")
        raise HTTPException(409, NO_OPEN_CASH)
    return journal


def require_cash_for_operation(user, session):
    """Toda nueva operación en efectivo exige una jornada abierta.

    inicioControl delimita la auditoría histórica, pero no desactiva esta regla
    cuando las colecciones de Caja están vacías.
    """
    return lock_open_journal(touch_register(user, session), user, session)


def _check_fingerprint(document, field, expected):
    if document.get(field) != expected:
        raise HTTPException(409, "El identificador de operación ya se utilizó con otros datos.")


def append_movement(journal, user, session, *, event_id, kind, direction, amount,
                    description, source_type="MANUAL", source_id=None, **details):
    """El llamador bloquea la jornada en la MISMA transacción."""
    value = money(amount)
    if value <= ZERO:
        raise HTTPException(422, "El movimiento debe ser mayor a cero.")
    now = _now()
    movement = {"_id": ObjectId(), "cajaId": journal["cajaId"], "jornadaId": journal["_id"],
                "local": user["local"], "tipo": kind, "naturaleza": direction,
                "monto": Decimal128(value), "fecha": now, "created_at": now,
                "eventoId": event_id, "origenTipo": source_type, "origenId": source_id,
                "descripcion": description, "usuarioId": user["_id"],
                "usuarioNombre": user["username"], **details}
    cashMovementsDb.insert_one(movement, session=session)
    return movement


def journal_summary(journal, session=None):
    groups = cashMovementsDb.aggregate([
        {"$match": {"local": journal["local"], "jornadaId": journal["_id"]}},
        {"$group": {"_id": {"tipo": "$tipo", "naturaleza": "$naturaleza"}, "monto": {"$sum": "$monto"}}}
    ], session=session)
    summary = {key: ZERO for key in ("ventasEfectivo", "gastosEfectivo", "otrosIngresos", "retiros",
        "ajustesEntrada", "ajustesSalida", "retiroCierre", "ingresos", "egresos")}
    for group in groups:
        kind, direction = group["_id"]["tipo"], group["_id"]["naturaleza"]
        amount = money(group["monto"])
        key = {"VENTA_EFECTIVO": "ventasEfectivo", "GASTO_EFECTIVO": "gastosEfectivo",
               "INGRESO_MANUAL": "otrosIngresos", "RETIRO": "retiros",
               "AJUSTE_ENTRADA": "ajustesEntrada", "AJUSTE_SALIDA": "ajustesSalida",
               "RETIRO_CIERRE": "retiroCierre"}[kind]
        summary[key] += amount
        # Contar primero y retirar después evita restar dos veces el retiro al cierre.
        if kind != "RETIRO_CIERRE":
            summary["ingresos" if direction == "INGRESO" else "egresos"] += amount
    summary["saldoEsperado"] = money(journal["montoApertura"]) + summary["ingresos"] - summary["egresos"]
    summary["saldoTrasRetiro"] = summary["saldoEsperado"] - summary["retiroCierre"]
    return summary


def _journal_detail(journal, session=None):
    return {**journal, "resumen": journal_summary(journal, session)}


def open_journal(data: CashOpening, user):
    operation, digest = str(data.operacionId), fingerprint(data.model_dump(mode="json"))
    def write(session):
        existing = cashJournalsDb.find_one({"local": user["local"], "operacionApertura": operation}, session=session)
        if existing:
            _check_fingerprint(existing, "huellaApertura", digest)
            return _journal_detail(existing, session)
        register = touch_register(user, session)
        if cashJournalsDb.find_one({"cajaId": register["_id"], "estado": "ABIERTA"}, session=session):
            raise HTTPException(409, "Ya existe una jornada de caja abierta en este local.")
        previous = cashJournalsDb.find_one({"cajaId": register["_id"], "estado": "CERRADA"},
            sort=[("fechaCierre", -1), ("_id", -1)], session=session)
        expected = money(previous["fondoSiguiente"]) if previous else None
        now = _now()
        journal = {"_id": ObjectId(), "cajaId": register["_id"], "cajaNombre": register["nombre"],
            "local": user["local"], "estado": "ABIERTA", "fechaApertura": now,
            "montoApertura": Decimal128(data.montoApertura), "usuarioAperturaId": user["_id"],
            "usuarioAperturaNombre": user["username"], "observacionApertura": data.observaciones,
            "jornadaAnteriorId": previous["_id"] if previous else None,
            "fondoEsperado": Decimal128(expected) if expected is not None else None,
            "diferenciaApertura": Decimal128(data.montoApertura - expected) if expected is not None else None,
            "fechaCierre": None, "usuarioCierreId": None, "usuarioCierreNombre": None,
            "saldoEsperado": None, "montoContado": None, "diferencia": None, "fondoSiguiente": None,
            "observacionCierre": None, "operacionApertura": operation, "huellaApertura": digest,
            "version": 0, "created_at": now, "updated_at": now}
        cashJournalsDb.insert_one(journal, session=session)
        if register.get("inicioControl") is None:
            cashRegistersDb.update_one({"_id": register["_id"]}, {"$set": {"inicioControl": now}}, session=session)
        return _journal_detail(journal, session)
    return serialize(transaction(write))


def manual_movement(journal_id, data: CashManualMovement, user, direction):
    if direction not in ("INGRESO", "EGRESO"):
        raise ValueError("Naturaleza de movimiento no admitida")
    journal_id = object_id(journal_id)
    event_id = f"MANUAL:{data.operacionId}"
    digest = fingerprint({**data.model_dump(mode="json"), "jornadaId": str(journal_id), "naturaleza": direction})
    def write(session):
        existing = cashMovementsDb.find_one({"local": user["local"], "eventoId": event_id}, session=session)
        if existing:
            _check_fingerprint(existing, "huella", digest)
            return existing
        register = touch_register(user, session)
        journal = lock_open_journal(register, user, session, journal_id)
        return append_movement(journal, user, session, event_id=event_id,
            kind="INGRESO_MANUAL" if direction == "INGRESO" else "RETIRO", direction=direction,
            amount=data.monto, description=data.motivo, observaciones=data.observaciones, huella=digest)
    return serialize(transaction(write))


def close_journal(journal_id, data: CashClosing, user):
    journal_id = object_id(journal_id)
    digest, operation = fingerprint(data.model_dump(mode="json")), str(data.operacionId)
    def write(session):
        previous = cashJournalsDb.find_one({"_id": journal_id, "local": user["local"]}, session=session)
        if previous is None:
            raise HTTPException(404, "No se encontró la jornada de caja.")
        if previous["estado"] == "CERRADA":
            if previous.get("operacionCierre") != operation:
                raise HTTPException(409, "Esta jornada ya está cerrada.")
            _check_fingerprint(previous, "huellaCierre", digest)
            return _journal_detail(previous, session)
        register = touch_register(user, session)
        journal = lock_open_journal(register, user, session, journal_id, data.version)
        summary = journal_summary(journal, session)
        withdrawal = data.montoContado - data.fondoSiguiente
        if withdrawal > ZERO:
            append_movement(journal, user, session, event_id=f"CIERRE:{journal_id}",
                kind="RETIRO_CIERRE", direction="EGRESO", amount=withdrawal,
                description="Retiro al cierre: efectivo contado menos fondo siguiente",
                source_type="CIERRE", source_id=journal_id)
        now = _now()
        update = {"estado": "CERRADA", "fechaCierre": now, "usuarioCierreId": user["_id"],
            "usuarioCierreNombre": user["username"], "saldoEsperado": Decimal128(summary["saldoEsperado"]),
            "montoContado": Decimal128(data.montoContado),
            "diferencia": Decimal128(data.montoContado - summary["saldoEsperado"]),
            "fondoSiguiente": Decimal128(data.fondoSiguiente), "retiroCierre": Decimal128(withdrawal),
            "observacionCierre": data.observaciones, "operacionCierre": operation,
            "huellaCierre": digest, "updated_at": now}
        cashJournalsDb.update_one({"_id": journal_id, "estado": "ABIERTA"}, {"$set": update}, session=session)
        return _journal_detail({**journal, **update}, session)
    return serialize(transaction(write))


def current_cash(user):
    def read(session):
        register = cashRegistersDb.find_one({"local": user["local"], "codigo": "PRINCIPAL"}, session=session)
        if register is None:
            return {"caja": None, "jornada": None, "ultimoCierre": None, "fondoSugerido": ZERO}
        scope = {"cajaId": register["_id"], "local": user["local"]}
        opened = cashJournalsDb.find_one({**scope, "estado": "ABIERTA"}, session=session)
        closed = cashJournalsDb.find_one({**scope, "estado": "CERRADA"},
            sort=[("fechaCierre", -1), ("_id", -1)], session=session)
        return {"caja": register, "jornada": _journal_detail(opened, session) if opened else None,
                "ultimoCierre": closed, "fondoSugerido": closed["fondoSiguiente"] if closed else ZERO}
    return serialize(transaction(read))


def get_journal(journal_id, user):
    journal_id = object_id(journal_id)
    def read(session):
        journal = cashJournalsDb.find_one({"_id": journal_id, "local": user["local"]}, session=session)
        if journal is None:
            raise HTTPException(404, "No se encontró la jornada de caja.")
        return _journal_detail(journal, session)
    return serialize(transaction(read))


def history(user, page=1, xpage=10, fecha_desde=None, fecha_hasta=None, estado=None):
    query = {"local": user["local"]}
    dates = date_filter(fecha_desde, fecha_hasta)
    if dates:
        query["fechaApertura"] = dates
    if estado:
        query["estado"] = estado
    def read(session):
        total = cashJournalsDb.count_documents(query, session=session)
        rows = cashJournalsDb.find(query, session=session).sort([("fechaApertura", -1), ("_id", -1)]).skip((page - 1) * xpage).limit(xpage)
        return {"items": [_journal_detail(row, session) for row in rows], "total": total, "page": page, "xpage": xpage}
    return serialize(transaction(read))


def movements(journal_id, user, page=1, xpage=10, fecha_desde=None, fecha_hasta=None,
              tipo=None, naturaleza=None, origen_tipo=None):
    journal_id = object_id(journal_id)
    query = {"local": user["local"], "jornadaId": journal_id}
    dates = date_filter(fecha_desde, fecha_hasta)
    if dates:
        query["fecha"] = dates
    for key, value in (("tipo", tipo), ("naturaleza", naturaleza), ("origenTipo", origen_tipo)):
        if value:
            query[key] = value
    def read(session):
        if not cashJournalsDb.find_one({"_id": journal_id, "local": user["local"]}, session=session):
            raise HTTPException(404, "No se encontró la jornada de caja.")
        total = cashMovementsDb.count_documents(query, session=session)
        rows = cashMovementsDb.find(query, session=session).sort([("fecha", -1), ("_id", -1)]).skip((page - 1) * xpage).limit(xpage)
        items = list(rows)
        for source_type, collection in (("VENTA", salesDb), ("GASTO", expensesDb)):
            ids = [row["origenId"] for row in items if row["origenTipo"] == source_type and row.get("origenId")]
            sources = {doc["_id"]: doc for doc in collection.find(
                {"local": user["local"], "_id": {"$in": ids}},
                {"anulado": 1, "auditoria": 1}, session=session)} if ids else {}
            for row in items:
                if row["origenTipo"] != source_type:
                    continue
                source = sources.get(row.get("origenId"), {})
                row["origenAnulado"] = source.get("anulado", False)
                row["correccionPosterior"] = any(change.get("sinMovimiento") and
                    change.get("jornadaId") == journal_id
                    for audit in source.get("auditoria", []) for change in audit.get("cambios", []))
        return {"items": items, "total": total, "page": page, "xpage": xpage}
    return serialize(transaction(read))
