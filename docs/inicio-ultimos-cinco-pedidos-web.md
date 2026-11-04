# Inicio: últimos cinco pedidos WEB

El bloque «Mis pedidos» del inicio muestra hasta cinco pedidos creados desde la web (`orders.origen_pedido = B2B`), ordenados por número WEB de mayor a menor. Incluye todo el historial y todos los estados, también entregados y facturados; no se limita a los pedidos activos ni a los creados hoy. El contador coincide con las tarjetas visibles. No se completa con pedidos de tienda si hay menos de cinco.

El inicio consulta `/api/v1/orders?state=TODOS&recent_web=true`. La selección del cliente y la restricción de subusuarios a sus propios pedidos se aplican antes del límite SQL de cinco. La sincronización reutiliza la lógica de estados y vinculación por llave completa; solo consulta los números seleccionados y sus albaranes. Un pedido EXIT sin cabecera WEB asociada no se importa como consecuencia de esta consulta.

Los números WEB se generan con año y secuencia de siete dígitos, por lo que su orden descendente en SQL mantiene el orden numérico. La tarjeta utiliza `web_number` y vuelve a filtrar por origen y limitar a cinco para evitar resultados mezclados. El refresco sigue conservando datos mientras llegan los nuevos resultados, sin parpadeo. No se borra ningún pedido; si uno de los originales ya no está en EXIT se conserva con el estado correspondiente.
