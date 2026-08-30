"""Ejecutar: python -m scripts.ensure_cash_indexes.
Crea índices de Caja e idempotencia de Ventas/Gastos en almacen; no carga ni migra documentos históricos.
"""
from app.services.cash_service import ensure_indexes

if __name__ == "__main__":
    ensure_indexes()
    print("Índices de Caja de almacen verificados.")
