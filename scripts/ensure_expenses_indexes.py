"""Ejecutar desde la raíz: python -m scripts.ensure_expenses_indexes.

Solo crea índices en almacen.expenses. No borra ni migra documentos.
"""
from app.db.mongo import expensesDb


def ensure_indexes():
    if expensesDb.full_name != "almacen.expenses":
        raise RuntimeError("Este script solo admite almacen.expenses.")
    # El listado siempre filtra por local y ordena por fecha/id.
    expensesDb.create_index([("local", 1), ("fecha", -1), ("_id", -1)], name="expenses_local_fecha")


if __name__ == "__main__":
    ensure_indexes()
    print("Índice de almacen.expenses verificado.")

