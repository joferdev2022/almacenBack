# Conteo de productos mediante Excel

El archivo `.xlsx` representa el conteo completo de un local. No se suman las
cantidades al stock actual. Los productos ausentes quedan con stock cero y
conservan sus registros, identificadores y demás datos.

La descarga ordena las columnas así:

`CODIGO, CANTIDAD, PRODUCTO, PRESENTACION, MARCA, CATEGORIA, DESCRIPCION, P. UNITARIO, P. VENTA`

- `CODIGO` contiene el identificador existente del producto, como texto. Se
  conserva al editar la descarga. Para productos nuevos se deja vacío.
- Los archivos anteriores sin código se vinculan por nombre y presentación,
  siempre que exista una sola coincidencia en el local.
- `CANTIDAD` vacía equivale a cero. Debe ser un entero no negativo.
- `PRODUCTO`, `PRESENTACION`, `P. UNITARIO` y `P. VENTA` son obligatorios en
  cada fila, tanto para productos existentes como nuevos.
- Los precios deben ser números no negativos. Un cero explícito es válido;
  una celda vacía es un error.
- `MARCA`, `CATEGORIA` y `DESCRIPCION` pueden quedar vacías.
- Se rechazan nombres y presentaciones duplicados aunque los códigos difieran.
  Se comparan sin diferencias de mayúsculas, espacios repetidos o formas
  equivalentes de unidades, como `LT`/`LITRO` y `250ml`/`250 MILILITROS`.
- Se rechazan códigos desconocidos, de otro local o repetidos. Una fila no puede
  crear una duplicidad con otro producto del catálogo.
- Una fila completamente vacía se ignora; una fila incompleta se informa con su
  número original de Excel. Los encabezados faltantes o repetidos, archivos sin
  productos y celdas con fórmulas o errores bloquean la carga.

`POST /api/products/preview-excel` recibe `file` y `local` como formulario.
Devuelve `valid`, `errors` (fila, columna y mensaje), un resumen, la vista previa
y `catalog_version`. No escribe en la base de datos.

`POST /api/products/upload-excel` recibe el mismo archivo y local. La interfaz
envía además `catalog_version` de la vista previa. El servidor valida todas las
filas otra vez antes de escribir. Los errores se devuelven como HTTP 422; un
catálogo que cambió desde la vista previa devuelve HTTP 409 y requiere revalidar.
La respuesta exitosa informa cuántos productos son nuevos, existentes y ausentes.

Después de completar las escrituras se guarda un registro en la colección
`importaciones_productos`: `local`, `filename`, `imported_at` (fecha BSON en UTC,
generada por el servidor) y los cuatro contadores de la respuesta. Las vistas
previas y las cargas rechazadas o fallidas no crean registros exitosos.

`GET /api/products/imports/latest?local=1` devuelve `data` con la última importación
del local, ordenada por fecha y luego por ID. Si no existen registros devuelve
`data: null`. La fecha de la respuesta es ISO 8601 en UTC. Productos consulta este
endpoint al abrirse y después de cada carga exitosa; muestra la fecha en horario
de Lima junto al archivo y el resumen. Recargar la página conserva la información
porque su origen es MongoDB. Los datos de importaciones antiguas no se inventan.

Una revisión del archivo sin consultar el catálogo no detecta duplicados ya
registrados en MongoDB. La validación del sistema sí los comprueba y bloquea la
carga. En ese caso, cada error incluye `conflicts` con los códigos, nombres,
presentaciones, stocks y categorías de las coincidencias del mismo local. La
pantalla muestra esos registros para poder revisar la duplicidad; no elige uno,
fusiona historiales ni elimina productos automáticamente. Añadir un código no
omite la comprobación de nombre y presentación duplicados en el catálogo.

No se añadieron transacciones ni historial por producto. La versión del catálogo
comprueba cambios anteriores al inicio de la aplicación; no bloquea movimientos
concurrentes durante las escrituras.

Pruebas aisladas, sin MongoDB real:

`python -m unittest discover -s tests -p test_product_excel.py -v`
