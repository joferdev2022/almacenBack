# Dosificación de productos

Las dosificaciones pertenecen al ID del producto y a su local. No se generan
dosis automáticamente: se registra el texto de la etiqueta o ficha técnica.
Cada uso contiene cultivo/uso, objetivo opcional, dosis, base de aplicación,
forma de aplicación, observaciones y fuente. Cultivo/uso, dosis y base son
obligatorios; se permiten hasta 50 usos por producto.

- `GET /api/products/{id}/dosages`: usuarios autenticados consultan productos de
  su propio local. Devuelve producto, dosificaciones, versión, permiso de
  edición y fecha/usuario de la última actualización. Los productos anteriores
  empiezan con una lista vacía y versión 0, sin migración.
- `PUT /api/products/{id}/dosages`: solo administradores (`permissions: 1`) del
  local del producto. Recibe `version` y la lista completa `dosificaciones`.
  Una lista vacía permite quitar todos los usos al guardar explícitamente.
- La versión se comprueba de forma atómica al escribir. Un cambio concurrente
  devuelve HTTP 409; el panel conserva el borrador y permite descartarlo para
  recargar. IDs inválidos devuelven 400 y productos ausentes/de otro local 404.

Se guardan en el mismo documento de `almacen.products`: `dosificaciones`,
`dosificacionesVersion`, `dosificacionesActualizadasEn` (fecha UTC del servidor)
y `dosificacionesActualizadasPor` (ID y nombre del usuario autenticado). La
respuesta serializa la fecha en horario de Lima y el frontend la presenta allí.
Solo se modifican estos campos; no se cambian stock, precios ni datos de ventas.

No se añade este campo al modelo general de edición del producto: sus valores
predeterminados no deben reemplazar las dosificaciones. La edición manual y el
importador Excel actualizan campos explícitos con `$set` y conservan estos datos,
incluidos los productos ausentes del Excel que pasan a stock cero. Para mantener
la asociación en próximas importaciones se conservan los códigos del producto.

El listado no carga las dosificaciones. Se consultan al abrir el panel lateral,
desde el botón con el icono de frasco en Acciones. La consulta no requiere el PIN
del historial. El servidor decide si se muestra la edición. Guardar confirma los
cambios; Cancelar descarta el borrador. La fecha y el usuario se muestran al pie.
