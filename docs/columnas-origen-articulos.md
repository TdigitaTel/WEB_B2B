# Origen de artículos en columnas

Las filas de cliente muestran tres checks sin texto repetido, alineados con las cabeceras WEB / Tienda / Eliminado. Operaciones usa WEB / EXIT / Eliminado. Tienda significa que la línea ya está registrada en tienda; no indica que se haya recogido. Los indicadores son de solo lectura. Un origen histórico desconocido conserva la marca mixta, sin atribuirlo automáticamente a WEB por el origen de la cabecera.

El checkout ya fija `OrderItem.created_in_web=True` al convertir los artículos del carrito en líneas del pedido, incluidos los borradores. La sincronización mantiene el valor; las nuevas líneas importadas directamente de EXIT siguen siendo False. Una prueba del flujo real de carrito comprueba WEB marcado y registro en tienda aún desmarcado.

## Reparación confirmada por el usuario

`app/data/confirmed_web_line_origins.json` contiene solo:

- WEB-2026-0000321 / EXIT 2026-AL-6008552, cliente 11264: 23622, 23493, 23508 y 22498.
- WEB-2026-0000260 / EXIT 2026-AL-6007768, cliente 11264: 21679 y 23538.

Bootstrap aplica la reparación al desplegar, si existen esas líneas y coinciden pedido WEB único, cliente, origen B2B y vínculo EXIT. Solo marca `created_in_web=True`; conserva cantidades, precios, previsiones, situación, marca de baja y fecha de sincronización. Cada cambio queda auditado y no se repite en reinicios posteriores. Si un código aparece varias veces no se elige una fila arbitraria: queda pendiente de revisión. El artículo 23568 y cualquier otra línea no incluida permanecen intactos.

Para comprobar el entorno antes de aplicar manualmente: `python -m app.repair_web_line_origins`. Sin argumentos solo muestra los cambios propuestos. Con `--apply` guarda la misma corrección auditada. No es una actualización general de todos los pedidos WEB.

La validación local utiliza datos simulados; los cambios de los dos pedidos reales se aplicarán al desplegar en la base de datos correspondiente. No se han modificado datos de producción desde la validación local.
