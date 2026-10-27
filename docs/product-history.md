# Historial de productos de almacén

Se conservan todos los eventos en `almacen.product_history`, con valores anteriores
y nuevos solamente de los campos modificados. El servidor asigna la fecha y la
identidad del login. Las llamadas antiguas sin una identidad válida se registran
como «Sin usuario identificado»; no se agregan restricciones de roles al CRUD.

Se registran creación, edición manual, eliminación y cambios de stock por crear,
editar o anular ventas. Cada evento se confirma en la misma transacción que la
operación. No se crean eventos retroactivos. La importación de Excel sigue
pendiente: reemplaza los productos con nuevos identificadores y no genera eventos.
Los registros de productos eliminados se conservan, aunque el panel de la tabla
solo abre productos existentes. No se cambia la edición de stock ni se añaden
controles de versión o un nuevo flujo de ajustes.

## PIN y consulta

`POST /api/products/{id}/history` recibe `{ "pin": "…" }`, exige login y limita
la consulta al local del usuario. Devuelve los tres eventos más recientes y el
total de registros. No acepta escrituras al historial desde el cliente.

Configurar `PRODUCT_HISTORY_PIN_HASH` en las variables de entorno del servidor
o ejecutar `venv\Scripts\python.exe tools\configure_product_history_pin.py` para
generarlo interactivamente en el `.env` ignorado por Git. No existe PIN por defecto.
Reiniciar el backend después de configurarlo. En despliegue configurar la misma
variable mediante el gestor de secretos.

Se admiten cinco intentos por usuario en cinco minutos por proceso. Si se usan
varios workers, compartir este límite en un almacén central antes del despliegue.
Los flujos antiguos de PIN quedan pendientes de migración al servidor.

## Validación local sin datos reales

`venv\Scripts\python.exe -m unittest discover -s tests -p test_product_history.py -v`

La suite usa persistencia en memoria y cubre retención, límite de tres, identidad,
PIN, aislamiento por local, stock, reintentos y rollback. No sustituye una prueba
de transacciones en un MongoDB de staging.
