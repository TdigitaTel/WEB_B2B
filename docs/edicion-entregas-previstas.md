# Edición de entregas previstas por operador

En Operaciones → Pedidos WEB, abrir el detalle del pedido:

- «Editar fecha prevista y observaciones» permite modificar fecha, hora y observaciones de cabecera. Se guarda en los campos existentes `orders.attention_deadline_at` (UTC) y `orders.notes`. La fecha se presenta en horario de España peninsular y las observaciones se muestran también al cliente.
- «Editar entregas previstas» abre las líneas con su fecha y hora directamente editables, junto con situación y observación. Guardar confirma cada línea y Deshacer recupera los valores anteriores. Se conserva `order_line_planning.lines[line_key].expected_at`, `observation` y `manual=true`.

Cabecera y líneas son independientes: editar una no sobrescribe las otras. La recogida programada/inmediata y lo servido en EXIT no cambian. Las fechas manuales por línea no se recalculan al consultar. La cabecera continúa guardada hasta su edición o un cambio explícito de recogida.

El cliente solo consulta; los endpoints de edición exigen operador/administrador y respetan delegaciones y permisos de pedidos. Los cambios se auditan. La cabecera rechaza modificaciones de pedidos ya atendidos/entregados/facturados y usa los valores originales para detectar ediciones concurrentes. Las líneas conservan su control de versión existente. No se precisa migración de base de datos.

PATCH `/api/v1/store/orders/{id}/planning`: `expected_at` con zona horaria, `observations` (hasta 1000 caracteres), `previous_expected_at` y `previous_observations`. Conflicto 409 si otro operador ha cambiado la cabecera. La ruta existente PATCH `/api/v1/store/orders/line-planning?order_id=...` conserva su contrato.

Verificación local: API con base de datos de pruebas, pruebas React de payloads de cabecera y líneas, error concurrente y conservación de edición, horario de Madrid en verano/invierno y hora inexistente al cambiar de horario. La previsualización visual usa pedidos simulados, sin cambiar datos de producción.
