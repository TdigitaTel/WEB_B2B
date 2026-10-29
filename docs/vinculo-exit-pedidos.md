# Vínculo normalizado del pedido web con EXIT

## Llave

La identidad del pedido EXIT es **CodigoEmpresa + EjercicioPedido + Serie + NumeroPedido**. El número se muestra por separado; una cadena como `2026/AL/6008375` es una referencia de compatibilidad, no la nueva llave.

En `orders` se reutiliza `company_code` para CodigoEmpresa (no se duplica la empresa) y se añaden `exit_order_year`, `exit_series`, `exit_order_number`. El índice único `ix_orders_exit_key` usa esos cuatro campos. Admite pedidos todavía sin vínculo mientras los campos opcionales estén a NULL. Una serie vacía es válida y se distingue de NULL (dato desconocido). No se inventa ejercicio ni serie cuando solo llega un número.

`order_items.order_id` es la clave foránea a `orders.id`: las líneas heredan la llave, sin copiar cuatro valores por línea. `exit_line_number`, opcional, identifica la línea de EXIT cuando la fuente lo proporciona; no se utiliza el SKU como identidad de línea. Las respuestas del API muestran los cuatro campos también en cada detalle mediante su cabecera. En SQL puede consultarse así:

```sql
SELECT o.company_code AS exit_company_code,
       o.exit_order_year, o.exit_series, o.exit_order_number,
       i.exit_line_number, i.*
FROM order_items i
JOIN orders o ON o.id = i.order_id;
```

## Robot: actualización compatible

Se mantiene `PATCH /api/v1/integrations/orders/estado`, autenticado con `X-Integration-Key` (`INTEGRATION_API_KEY`). Los nuevos campos son opcionales, pueden completarse en actualizaciones sucesivas y aparecen en GET `/api/v1/integrations/orders?include_items=true`. `exit_company_code` es el nombre del API para el campo existente `company_code`.

```json
{
  "order_id": "UUID PUBLICO DEL PEDIDO WEB",
  "estado_registro_exit": "REGISTRADO",
  "source": "RPA",
  "exit_company_code": 1,
  "exit_order_year": 2026,
  "exit_series": "AL",
  "exit_order_number": "6008375",
  "occurred_at": "2026-10-29T17:30:59+01:00"
}
```

Identificar el pedido web por `order_id` o su `order_number` WEB. No utilizar el número EXIT solo para localizarlo si puede repetirse en varias empresas/series/ejercicios. Una referencia ambigua recibe 409. La empresa EXIT debe coincidir con la empresa del pedido; no se cambia silenciosamente su sede/empresa. El número se envía como texto de dígitos para conservar ceros iniciales.

Se mantiene `nro_pedido_exit` para el robot anterior y para lectores de referencias/documentos. Temporalmente puede contener el formato antiguo. Con una llave completa, la referencia compatible se construye a partir de sus componentes. No requiere cambiar inmediatamente el robot. Completar la llave en un pedido ya REGISTRADO guarda los datos y devuelve `changed: true`, sin duplicar estados del historial; repetir los mismos datos devuelve `changed: false`. Un conflicto con otro pedido WEB recibe 409.

## Operaciones y lista del cliente

«Vincular EXIT» pide empresa, ejercicio, serie, número y fecha/hora real. El número es independiente de los otros campos; la serie puede estar vacía si así existe en EXIT. Volver a Pendiente borra el vínculo y el número de línea externo, conserva empresa/delegación y permite al robot volver a procesar el pedido.

El historial del cliente prioriza el pedido WEB cuando tiene también una proyección local EXIT, y muestra una sola ficha con los importes/detalle actuales de EXIT. Las proyecciones antiguas no se borran; su llave estructurada se libera en favor del pedido WEB original si es necesario. Se respetan cliente, empresa y delegación, y no se unen identidades completas de distintos ejercicios/series. Solo como compatibilidad, un número antiguo sin llave completa se empareja si no hay ambigüedad en el mismo ámbito y ejercicio; en otro caso debe completarse la llave. «Mis pedidos» abre con origen WEB y permite elegir Todos o No WEB.

## Despliegue y validación

El bootstrap agrega columnas y sustituye el índice único antiguo de `nro_pedido_exit` por la llave compuesta. No hay limpieza destructiva ni SQL manual; los datos históricos permanecen y se completan con el robot, Operaciones o una lectura inequívoca de EXIT. No se modifican pedidos en EXIT.

Pruebas con base desechable: cuatro campos opcionales, empresa existente reutilizada, clave heredada en detalles, estado repetido, identidad completa única, mismo número en otra serie/ejercicio, API anterior, desvinculación, copia EXIT existente y ausencia de lectura actual. La migración PostgreSQL y los datos reales deben verificarse al desplegar en desarrollo; las pruebas locales usan SQLite.
