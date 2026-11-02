# Reconciliación automática de pedidos con EXIT

El resumen de inicio y Mis pedidos reciben datos de GET `/api/v1/orders`. Se combinan `orders` de PostgreSQL con las cabeceras y líneas de EXIT. Antes se añadía la copia local incluso cuando EXIT ya no devolvía ese pedido.

Al consultar se usa la llave guardada (empresa, ejercicio, serie y número). Si está completa, la existencia se comprueba en `PedidoVentaCabecera` sin filtros de fecha, estado, delegación o límite TOP. Se agrupan hasta 200 llaves por consulta (800 parámetros), sin solicitar líneas ni stock. Las llaves presentes en la lectura actual no requieren otra consulta. No se infiere una eliminación por faltar en el rango de fechas.

Para cada llave se conserva el pedido WEB original. Si hay una sola cabecera WEB y copias locales de origen EXIT asociadas a esa misma llave, estas se retiran automáticamente de los resultados. Empresa, ejercicio y serie distintos no se mezclan por coincidir el número. Si la llave está incompleta, no se intenta adivinarla.

Si la consulta exacta confirma que un pedido vinculado no existe y no tiene entrega, estado atendido/entregado/facturado ni albarán conocido, se retira del listado. La verificación de albaranes debe haber terminado correctamente. Los pedidos WEB pendientes de registrar en EXIT se conservan. Un fallo de conexión o esquema no provoca un nuevo retiro por inexistencia.

Se usa baja lógica: `orders.reconciliation_hidden_at` y `reconciliation_reason` (DUPLICATE_EXIT o MISSING_EXIT). No se destruyen el pedido original, sus líneas ni su historial. Cada cambio queda en `audit_events` como ORDER_RECONCILED, con llave y pedido canónico. Las consultas siguientes son idempotentes. Si la llave vuelve a existir en EXIT, se recupera automáticamente el pedido principal; las copias duplicadas siguen retiradas.

La misma comprobación se aplica al tablero WEB del operador. Se ejecuta al consultar/refrescar, sin cron adicional. Bootstrap añade las dos columnas de forma idempotente en PostgreSQL. No requiere una limpieza SQL manual ni elimina datos en EXIT. La validación local usa una base de pruebas y mocks de EXIT; no se ha ejecutado sobre los pedidos de producción de las capturas.
