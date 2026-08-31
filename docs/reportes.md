# Reportes de ventas

Reportes de solo lectura, sin modificar productos, lotes, importaciones ni ventas.

## API y acceso

- `GET /api/reports/sales`: resumen, serie mensual, top 10 por cantidad e importe y tabla paginada.
- `GET /api/reports/sales/excel`: archivo XLSX con una hoja por mes/año, por ejemplo **enero2026**, **febrero2026**, en orden cronológico.
- Requieren Bearer token y permiso actual `permissions=1`. El local se obtiene del usuario autenticado; un `local` diferente se rechaza con 403. Las respuestas no se almacenan en caché.
- Se reutiliza la validación de identidad de Ventas/Caja/Gastos. También se hereda su excepción temporal existente para vencimiento de token; este módulo no modifica la política de autenticación.

Parámetros comunes: `fecha_desde`, `fecha_hasta` (YYYY-MM-DD, ambas inclusivas), `producto` (nombre histórico/actual o ID, sin distinguir acentos/mayúsculas), `categoria` (categoría del catálogo actual) y `ventas` (`todas`, por defecto, o `pagadas`). Sin fechas: desde el 1 de enero hasta hoy en Lima. `categoria=__sin_categoria__` selecciona históricos sin clasificación actual disponible. La consulta JSON añade `page` (desde 1) y `xpage` (1–100, por defecto 25). El Excel no se pagina.

## Definiciones

- Fuente: `sales.productos` por `fechaVenta`, zona `America/Lima`. MongoDB devuelve UTC sin zona; se interpreta como UTC, nunca como hora de Lima.
- Importe vendido: suma decimal de `cantidad × precioUnitario`, redondeada por línea a céntimos. **No** usar `precioTotal`: en créditos puede contener el saldo restante.
- `ventas=todas` incluye créditos y ventas pagadas; `ventas=pagadas` solo documentos con `estado=cancelado`, que significa **pagada**, no anulada. Incluye créditos completamente pagados y excluye los pendientes o con abonos parciales. Se usa siempre la fecha de venta, no la de pago. En ambas opciones se excluyen documentos con `anulado=true`.
- Número de ventas: documentos distintos con alguna línea que coincide con los filtros. No se suma el resto de la cesta al buscar un producto/categoría.
- Ventas vacías históricas: se omiten únicamente documentos con `productos=[]` y ambos campos `precioTotal` y `precioTotalOriginal` numéricos, finitos y exactamente cero. No se redondean importes ni se interpretan ausencias como cero. Campos faltantes, productos con estructura inválida o importes distintos de cero mantienen el error 422 con ID de venta. No se modifican registros, caja ni inventario.
- `resumen.ventasVaciasOmitidas` y `mensual[].ventasVaciasOmitidas` informan el recuento total y mensual. Si hay omisiones se muestran en `avisos` y al pie de cada hoja Excel afectada (incluida su impresión), sin alterar sus columnas. El recuento respeta local, fechas y tipo de ventas; no se puede asignar a producto/categoría porque esos documentos no tienen líneas. Las omitidas no suman número de ventas, cantidades, importes ni rankings.
- Venta promedio ponderada: importe del producto/mes dividido entre cantidad; se entrega con hasta 4 decimales. Los importes son los totales de las líneas, no el promedio redondeado multiplicado de nuevo.
- Precio de compra: valor registrado en `products.precioCompra`, vinculado exclusivamente por ID y local, sin promediar, multiplicar ni redondear su valor para el reporte. Cero es válido; un producto ausente o costo inválido produce `null`/«No disponible». Se incluye en el Excel, antes de P. VENTA, pero no en la tabla de pantalla. No se utiliza como costo histórico ni se calcula rentabilidad.
- Presentación: `products.unidadDeMedida`; marca, categoría y descripción: `marca`, `categoria` y `descripcion` del mismo producto actual. Los datos ausentes quedan vacíos en Excel. No se busca por nombre para reconstruir vínculos perdidos.
- Nombre: snapshot guardado en la venta. La tabla se agrupa por mes e ID de producto; IDs diferentes con el mismo nombre no se fusionan. Si una importación reemplaza los IDs, sus ventas anteriores se conservan, pero el costo/categoría actuales no se pueden atribuir con seguridad. Se mantiene esa ausencia de información explícita.
- Los meses sin ventas aparecen con cero en las series y tienen su propia hoja Excel sin productos. Tabla, indicadores, rankings y Excel aplican los mismos filtros; los totales son globales, no de la página visible.
- No se implementan devoluciones parciales, reconstrucción histórica ni lotes. Se respetan las anulaciones existentes.

## Límites y operación

Máximo 60 meses por consulta y 100 000 líneas coincidentes para la vista. El Excel admite 25 000 líneas de ventas para limitar memoria al construir sus hojas mensuales; al superar el límite responde 422 y pide reducir el período/producto, **sin entregar un archivo parcial**. Los datos históricos con cantidades/precios inválidos producen un error identificando la venta; no se ocultan ni se convierten silenciosamente en cero.

El servicio recorre documentos proyectados del período y agrupa en memoria, sin escrituras ni consultas por cada producto. Para volúmenes mayores conviene una agregación Mongo y exportación asíncrona/por streaming. Un índice existente o futuro de `sales(local, fechaVenta)` favorece la lectura; no se crean índices ni migraciones desde este módulo.

Cada hoja Excel comienza con estos encabezados en la primera fila: **CANTIDAD, PRODUCTO, PRESENTACION, MARCA, CATEGORIA, DESCRIPCION, P. COMPRA, P. VENTA, IMPORTE VENDIDO**. Contiene una fila por producto del mes, números tipados, encabezados congelados, tabla filtrable, total mensual y filtros aplicados al pie. P. VENTA es el promedio ponderado, explicado en un comentario del encabezado. No se incluye un aviso de compra referencial. Los textos se guardan explícitamente como texto para impedir inyección de fórmulas.

## Verificación

`python -m unittest discover -s tests -v`

Las pruebas usan `tests/memory_db.py`: no abren la conexión real, no alteran stock/caja y cubren fechas, promedios, créditos, anulaciones, local/permisos, catálogo reemplazado, paginación, XLSX y límites. No se requieren paquetes nuevos: se reutiliza `openpyxl` de requirements.txt.
