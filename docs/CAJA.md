# Caja de Almacén — implementación y verificación
Fecha: 28/08/2026.

Implementado en backend y Angular. Router registrado, índices verificados en MongoDB real.
No se abrió una jornada operativa del usuario ni se generaron movimientos históricos.
Para empezar: reiniciar el backend y Angular si no recargaron los cambios, entrar a **Caja** y abrir la primera jornada con el efectivo físico disponible.

## 1. Arquitectura encontrada

Angular 16 usa NgModules, rutas con carga diferida, Angular Material, Reactive Forms, MatDialog, SweetAlert2 y un DataService compartido.
FastAPI usa routers, servicios con PyMongo directamente y modelos Pydantic 2; no existe una capa de repositorios que deba reproducirse.
Las entidades de Almacén se relacionan con ObjectId y un campo local entero.
Las respuestas mantienen data, message y code; los listados antiguos de Ventas/Gastos conservan su envoltura.
Gastos ya utiliza Decimal128. Ventas conserva importes float y precioTotal como saldo de deuda mientras está a crédito.

Se reutilizaron los permisos y la identidad existentes de Gastos, incluyendo la excepción de expiración que se pidió para desarrollo.
El login, sus URL localhost y auth.service.ts no fueron modificados por este trabajo.
La ruta antigua de licorería importa sale_model.py: ese archivo se conservó sin cambios de contenido; Almacén usa ahora sales_model.py.

## 2. Diseño final

Una **Caja principal por local**, jornadas de apertura/cierre y movimientos de efectivo inmutables.
No hay formularios duplicados para registrar ventas o gastos desde Caja.
La integración se hace dentro de los servicios del backend, en la misma transacción que guarda la operación y, para Ventas, modifica stock.

La jornada de Caja no es una sesión de login: cerrar el navegador, salir del sistema o vencer un JWT no cierra Caja.
No se agregaron dependencias, frameworks visuales, bancos, contabilidad, cierre automático ni carga histórica.

## 3. Colecciones y documentos

Exclusivamente en la base **almacen**:

| Colección | Campos principales |
| --- | --- |
| cash_registers | _id, local, codigo=PRINCIPAL, nombre, activa, inicioControl, version, created_at, updated_at |
| cash_journals | _id, cajaId, cajaNombre, local, estado, fechaApertura, montoApertura, usuarioAperturaId/Nombre, observacionApertura, jornadaAnteriorId, fondoEsperado, diferenciaApertura, fechaCierre, usuarioCierreId/Nombre, saldoEsperado, montoContado, diferencia, fondoSiguiente, retiroCierre, observacionCierre, version, created_at, updated_at |
| cash_movements | _id, cajaId, jornadaId, local, tipo, naturaleza, monto, fecha, origenTipo, origenId, descripcion, observaciones cuando corresponde, usuarioId/Nombre, eventoId, created_at |

Jornadas guardan además operacionApertura/huellaApertura y, al cerrar, operacionCierre/huellaCierre.
Los movimientos manuales guardan una huella; los ajustes conservan movimientoOriginalId y jornadaOriginalId.
Las huellas internas no se exponen en las respuestas.

Importes de Caja: Decimal128; referencias: ObjectId; fechas: datetime UTC en MongoDB, ISO con zona de Lima en API.
Los filtros de días cubren el día completo en America/Lima.

Ventas y Gastos conservan sus colecciones sales y expenses.
Se añaden auditoria, operaciones idempotentes, version, anulado y datos de anulación.
El vínculo pagoCaja contiene controlado, jornadaId, monto firmado y movimientoId.
En Ventas cada cobro tiene su propio vínculo y método en pagos; no se atribuye a efectivo todo el importe de una venta con abonos de distintos métodos.
No se migraron documentos históricos.

## 4. Índices

Creados/verificados con nombres estables:

| Colección | Índice | Finalidad |
| --- | --- | --- |
| cash_registers | cash_register_local_code: local + codigo, único | Una caja principal por local |
| cash_journals | cash_one_open_journal: cajaId, único parcial estado=ABIERTA | Una sola jornada abierta |
| cash_journals | cash_opening_operation: local + operacionApertura, único | Reintentos de apertura |
| cash_journals | cash_journal_history: local + fechaApertura descendente + _id descendente | Historial paginado |
| cash_movements | cash_unique_event: local + eventoId, único | No duplicar movimientos |
| cash_movements | cash_journal_movements: local + jornadaId + fecha descendente + _id descendente | Movimientos paginados |
| cash_movements | cash_movement_source: local + origenTipo + origenId | Trazabilidad del origen |
| sales | sales_creation_operation: local + operacionCreacion, único parcial cuando es string | No duplicar ventas nuevas; no colisiona con documentos antiguos |
| expenses | expenses_creation_operation: local + operacionCreacion, único parcial cuando es string | No duplicar gastos nuevos |
| sales | sales_local_fecha: local + fechaVenta descendente + _id descendente | Listado de ventas |

Se verifican también al iniciar FastAPI. El aprovisionamiento comprueba los nombres completos almacen.coleccion antes de crear índices.
No se crearon índices en licoreria.

## 5. Archivos backend creados

```text
app/models/cash_model.py
app/models/payment_model.py
app/models/sales_model.py
app/routes/cash_route.py
app/services/cash_effects.py
app/services/cash_service.py
app/utils/cash_helpers.py
app/utils/operation_helpers.py
docs/CAJA.md
scripts/ensure_cash_indexes.py
scripts/verify_cash_integration.py
tests/memory_db.py
tests/test_cash.py
```

## 6. Archivos backend modificados

```text
app/db/mongo.py
app/models/expense_model.py
app/routes/expenses_route.py
app/routes/sales_route.py
app/services/dashboard_service.py
app/services/expenses_service.py
app/services/sales_service.py
app/services/seller_service.py
app/utils/helpers.py
main.py
tests/test_expenses.py
```

mongo.py solo incorpora las tres referencias de colecciones.
dashboard_service.py y seller_service.py excluyen ventas anuladas para mantener el efecto anterior del borrado sobre sus reportes, sin cambiar sus fórmulas.
El resto corresponde a integración de operaciones, contratos, serialización, auditoría y pruebas.

## 7. Archivos Angular creados

```text
src/app/components/modal-cash-operation/modal-cash-operation.component.html
src/app/components/modal-cash-operation/modal-cash-operation.component.scss
src/app/components/modal-cash-operation/modal-cash-operation.component.spec.ts
src/app/components/modal-cash-operation/modal-cash-operation.component.ts
src/app/components/operation-audit/operation-audit.component.ts
src/app/models/internal/cash.model.ts
src/app/pages/cash/cash-movements.component.html
src/app/pages/cash/cash-movements.component.scss
src/app/pages/cash/cash-movements.component.spec.ts
src/app/pages/cash/cash-movements.component.ts
src/app/pages/cash/cash-routing.module.ts
src/app/pages/cash/cash-summary.scss
src/app/pages/cash/cash-table.scss
src/app/pages/cash/cash.component.html
src/app/pages/cash/cash.component.scss
src/app/pages/cash/cash.component.ts
src/app/pages/cash/cash.module.ts
src/app/shared/cash.utils.ts
tsconfig.cash-spec.json
```

CashComponent resuelve caja actual, historial y detalle de jornada.
CashMovementsComponent maneja filtros y paginación.
ModalCashOperationComponent reutiliza un formulario para abrir, ingresar, retirar y cerrar.
OperationAuditComponent permite consultar el historial desde los detalles existentes.

## 8. Archivos Angular modificados

```text
src/app/components/components.module.ts
src/app/components/modal-credit-edit/modal-credit-edit.component.html
src/app/components/modal-credit-edit/modal-credit-edit.component.spec.ts
src/app/components/modal-credit-edit/modal-credit-edit.component.ts
src/app/components/modal-expense/modal-expense.component.ts
src/app/components/modal-info-expense/modal-info-expense.component.html
src/app/components/modal-info-sale/modal-info-sale.component.html
src/app/components/modal-info-sale/modal-info-sale.component.scss
src/app/components/modal-pay-expense/modal-pay-expense.component.spec.ts
src/app/components/modal-pay-expense/modal-pay-expense.component.ts
src/app/components/modal-sale/modal-sale.component.html
src/app/components/modal-sale/modal-sale.component.ts
src/app/components/sidebar/sidebar.component.html
src/app/interceptors/token.interceptor.ts
src/app/models/internal/expense.model.ts
src/app/models/internal/sale.model.ts
src/app/pages/credits/credits.component.ts
src/app/pages/expenses/expenses.component.html
src/app/pages/expenses/expenses.component.ts
src/app/pages/new-sale/new-sale.component.html
src/app/pages/new-sale/new-sale.component.ts
src/app/pages/pages-routing.module.ts
src/app/pages/sales/sales.component.html
src/app/pages/sales/sales.component.ts
src/app/services/data-expenses.service.spec.ts
src/app/services/data.service.ts
src/app/shared/expense-dialog.scss
src/styles.scss
```

Se reutilizaron DataService, Material, los detalles de Venta/Gasto y los estilos de diálogos de Gastos.
auth.service.ts ya tenía cambios del usuario al comenzar y se dejó intacto.
El interceptor únicamente evita interpretar un 403 de Caja/Ventas como una solicitud de renovación del login, siguiendo el comportamiento que Gastos ya tenía.

## 9. Endpoints

Todos bajo /api:

| Método | Ruta | Operación |
| --- | --- | --- |
| GET | /cash/current | Caja actual, jornada abierta, último cierre y fondo sugerido |
| GET | /cash/history | Historial paginado con fechas y estado |
| GET | /cash/{id} | Detalle y resumen de jornada |
| GET | /cash/{id}/movements | Movimientos paginados con fechas, tipo, naturaleza y origen |
| POST | /cash/open | Apertura |
| POST | /cash/{id}/income | Ingreso manual |
| POST | /cash/{id}/withdrawal | Retiro manual |
| POST | /cash/{id}/close | Cierre con conteo, fondo y versión |

Se conservaron las URL de Ventas y Gastos, ajustando sus escrituras:

- POST /sales y /expenses: operación integrada.
- PUT /sales/{id} y /expenses/{id}: edición con ajustes/auditoría.
- PUT /sales/payment/{id}: recibe monto, metodoPago y fechaPago, incluidos cobros finales.
- PUT /sales/state/{id}?state=credito: recibe motivo; corrige un cobro inexistente.
- PUT /expenses/{id}/pay: método y fecha de pago.
- DELETE /sales/{id} y /expenses/{id}: recibe motivo y **anula**, no elimina físicamente.
- GET /sales/{id}: consulta del origen desde Caja; Gastos conserva su detalle existente.

Las escrituras de Ventas/Gastos exigen encabezado Idempotency-Key UUID.
Las escrituras de Caja reciben operacionId UUID en el cuerpo.
Identidad y local provienen del usuario autenticado. Solo permissions=1 permite escribir; otros usuarios autenticados pueden consultar su local.

Rutas Angular: /almacen/caja, /almacen/caja/historial y /almacen/caja/jornadas/:id.

## 10. Integración de Ventas

cancelado conserva su significado histórico de **pagado**; no se confundió con anulado.
Una venta pagada genera un cobro. Solo EFECTIVO genera VENTA_EFECTIVO.
Una venta a crédito consume stock, pero no registra ingreso de efectivo hasta cobrar.
Cada abono, incluido el último, requiere monto, método y fecha; solo su parte en efectivo afecta Caja.
El detalle muestra los cobros y sus métodos reales, aunque difieran del método originalmente seleccionado.
Los cobros diarios se contabilizan una sola vez, incluidos los finales, en el indicador de cobros de créditos.

Venta, stock, cobro y movimiento se confirman o revierten juntos.
Editar importes/productos/métodos de una venta con abonos se rechaza para no reemplazar cobros ya realizados.
La API admite la edición de ventas sin ese conflicto; no se reconstruyó el editor general de Ventas.

## 11. Integración de Gastos

PAGADO + EFECTIVO produce un egreso GASTO_EFECTIVO.
PAGADO con Yape, Plin, transferencia, tarjeta u otro no mueve efectivo.
PENDIENTE no produce movimiento.
Al pagarse posteriormente, se registra el efecto con el método elegido.
Editar monto, estado o método genera el ajuste correspondiente mientras la jornada de ese pago permanece abierta.
La validación de importe positivo, dos decimales, método obligatorio si pagado y fecha de pago permanece en backend.

La lista de métodos y la regla de efectivo son compartidas por Ventas/Gastos.
No existe checkbox “afecta caja”.

## 12. Duplicados y concurrencia

El formulario mantiene un UUID durante los reintentos, se bloquea mientras guarda y evita doble envío.
Backend registra la huella del contenido: reutilizar el UUID con datos distintos devuelve 409.
Los índices únicos constituyen una segunda protección.

Las transacciones PyMongo usan snapshot y mayoría. Escrituras sobre la caja/jornada serializan aperturas, movimientos y cierres.
El cierre incluye la versión del resumen visto: si otro movimiento cambió el saldo, se rechaza y se solicita actualizar.
No hay alternativa silenciosa de escrituras parciales cuando MongoDB no admite transacciones.

## 13. Cálculo del saldo

Saldo esperado = apertura + ventas efectivo + ingresos manuales + ajustes de entrada − gastos efectivo − retiros − ajustes de salida.

Se reconstruye con los movimientos; no se guarda únicamente un saldo mutable.
El RETIRO_CIERRE queda separado para no restarlo antes del conteo y descontarlo dos veces.

Ejemplo verificado:
500 + 100 − 50 − 200 + 100 − 150 = **300**.
La venta Yape y el gasto por transferencia no cambian ese resultado.

## 14. Apertura y comienzo del control

Se solicita monto inicial igual o mayor a cero y observación opcional.
Si existe una jornada abierta del mismo local, otra apertura se rechaza.
La primera apertura marca inicioControl de forma atómica.
No recorre ni importa ventas o gastos anteriores.

Después de esa apertura, las nuevas operaciones en efectivo requieren jornada abierta.
No se impiden pagos no efectivos ni operaciones pendientes.
Cobrar ahora una deuda antigua o pagar ahora un gasto pendiente antiguo sí es una nueva operación de dinero.
La fecha elegida del pago no inserta movimientos en jornadas históricas: el movimiento corresponde a la jornada abierta durante su registro.

## 15. Cierre

Muestra esperado y desglose; solicita contado, fondo siguiente y observación.
Valida ambos importes y fondo siguiente <= contado.
Guarda esperado, contado, diferencia, retiro, fondo, usuario y fecha.
Genera RETIRO_CIERRE = contado − fondo, si el resultado es positivo.
La jornada pasa a CERRADA y no acepta movimientos nuevos.
Repetir el mismo cierre no repite el retiro.

## 16. Fondo siguiente

El último cierre sugiere el monto de apertura siguiente.
Se permite declarar una cantidad distinta, guardando fondoEsperado y diferenciaApertura.
No se modifica el cierre anterior.

Ejemplo: esperado 300, contado 295, fondo 200 → diferencia −5 y retiro 95.
La próxima apertura sugiere 200.
El saldo teórico tras el retiro es 205: con la diferencia de −5, el fondo físico es 200. No se oculta la diferencia forzando movimientos.

## 17. Diferencias y correcciones

Las diferencias de conteo se guardan explícitamente; no se alteran movimientos para cuadrarlas.
Si una corrección pertenece a una jornada aún abierta, se genera AJUSTE_ENTRADA o AJUSTE_SALIDA con referencia al movimiento original.
Si el pago pertenece a una jornada ya cerrada, la corrección es documental: conserva el cierre y deja auditoría marcada sinMovimiento.
La tabla avisa “Corregido después del cierre” y permite abrir el origen.

En particular, pasar una venta pagada a crédito significa que el cobro nunca ocurrió:
restablece la deuda, marca sus cobros como corregidos y no inventa una devolución en una jornada posterior.
Esto evita descontar otra vez un faltante que ya quedó registrado en el conteo anterior.

## 18. Anulaciones autorizadas

Ventas y Gastos se conservan con anulado=true, motivo, usuario y fecha.
Los movimientos originales nunca se borran.
Si la operación tuvo efectivo controlado, anular registra su reversión en la jornada actualmente abierta.
En una venta también se devuelve stock una sola vez.
Si no hay jornada abierta, la anulación con reversión de efectivo se rechaza sin cambios parciales.

La confirmación pide motivo y explica que se revertirá el dinero.
Anular una operación implica esa reversión; corregir un cobro que nunca ocurrió usa la acción de corrección, no una devolución.
Las operaciones previas al inicio del control no generan movimientos retroactivos al anularse.

## 19. Pruebas realizadas

- **54 pruebas backend aprobadas**: reglas, API, permisos, locales, fechas, importes, reintentos, rollback, edición, anulaciones, reportes y los 15 casos solicitados.
- **41 pruebas Angular aprobadas**: Gastos, Caja, créditos, filtros, peticiones HTTP, doble envío, versión de cierre, errores y detalle de métodos.
- **MongoDB real**: flujo completo hasta esperado 300 / contado 295 / fondo 200; aperturas simultáneas; venta repetida simultáneamente; rollback después de stock y movimiento; anulación/edición; cierre concurrente con movimiento.
- Las pruebas reales usaron únicamente colecciones temporales codex_cash_test_* dentro de almacen, eliminadas al terminar. No escribieron ventas, gastos, stock ni jornadas operativas reales.
- Inicio real de FastAPI, generación de OpenAPI y rutas montadas verificados; peticiones sin usuario a Caja, Ventas y Gastos siguen rechazadas.
- Compilación Angular de producción aprobada.
- **14 escenarios visuales** con componentes reales y datos ficticios: escritorio, móvil 390/320 px, apertura, caja cerrada, historial, detalle, cierre, retiro y error; sin desbordamiento horizontal de página. Se probaron filtros y cálculo de cierre mediante interacción real.
- La comprobación visual usó un navegador aislado porque el navegador integrado no pudo iniciarse. No se usó la sesión del usuario.
- Las pruebas de interfaz son focalizadas; no se certifica la suite global de módulos ajenos a este cambio.

Comandos desde cada proyecto, con su entorno habitual:

```powershell
# Backend, sin tocar MongoDB
.\venv\Scripts\python.exe -m unittest discover -s tests -v

# Aprovisionar/verificar índices solo de almacen
.\venv\Scripts\python.exe -m scripts.ensure_cash_indexes

# Integración real: crea y elimina sus propias colecciones temporales
.\venv\Scripts\python.exe -m scripts.verify_cash_integration

# Frontend
npx ng build --configuration=production
npx ng test --watch=false --browsers=ChromeHeadless --ts-config=tsconfig.cash-spec.json --include="src/app/pages/cash/*.spec.ts" --include="src/app/components/modal-cash-operation/*.spec.ts" --include="src/app/components/modal-credit-edit/*.spec.ts" --include="src/app/services/data-expenses.service.spec.ts" --include="src/app/components/modal-expense/*.spec.ts" --include="src/app/components/modal-pay-expense/*.spec.ts" --include="src/app/pages/expenses/*.spec.ts"
```

## 20. Riesgos y siguientes pasos

1. Actualizar/reiniciar frontend y backend juntos: las escrituras incorporan idempotencia y el cobro de créditos ahora envía monto, método y fecha.
2. Abrir la primera jornada con un conteo físico real. No se activó esa jornada por cuenta del usuario.
3. MongoDB debe seguir disponible y admitir transacciones. Se verificó esa capacidad; hubo un fallo DNS intermitente durante una conexión de prueba, sin cambios en la configuración del proyecto.
4. Antes de producción, revisar la política de expiración del login que se mantiene por instrucción del usuario. Caja no añade vencimientos ni cierres por autenticación.
5. Las correcciones posteriores a un cierre son documentales; las devoluciones reales se reflejan mediante anulación o movimiento propio de Caja según corresponda. No se reabren jornadas.
6. Si se borró previamente un producto del catálogo, una anulación conserva su historia pero no recrea ese producto ni su stock. No se cambió globalmente la eliminación de productos.
7. Los listados operativos excluyen anulados; el origen permanece consultable por ID y desde sus movimientos de Caja. Un buscador general de anulados puede añadirse después.
8. La compilación muestra advertencias de tamaño de estilos/bundle y CommonJS existentes en la configuración; no hubo errores. No se aumentaron los presupuestos para ocultarlas.
9. Una futura ampliación puede añadir varias cajas por local, arqueo por denominaciones o exportación de cierres, conservando cajaId, jornadaId, origen y eventos idempotentes. No forman parte de esta entrega.
