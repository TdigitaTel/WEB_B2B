# Búsqueda individual de pedidos

Mis pedidos comienza con un intervalo de un mes natural hasta hoy (zona Europe/Madrid); si el mes anterior no tiene el mismo día, usa su último día. Estado Todos y origen WEB por defecto.

El campo Código WEB o número EXIT busca el código WEB completo o el número EXIT exacto, sin ejercicio ni serie. La búsqueda individual ignora fechas, estado y origen. Vaciar el campo y consultar vuelve al listado filtrado. No altera la vinculación de cuatro campos con EXIT.

GET /api/v1/orders?order_query=WEB-2026-0000286
GET /api/v1/orders?order_query=6008375

La consulta conserva el cliente autenticado y la restricción de pedidos propios. Si un número EXIT se repite en varias empresas, ejercicios o series del cliente, muestra las coincidencias: no supone que el número sea una llave única. La búsqueda en EXIT incluye cliente y número en SQL y omite el intervalo de fechas.

Los resultados se ordenan por número descendente, usando el número EXIT si existe y la secuencia WEB en caso contrario; desempate por fecha. Las consultas normales mantienen sus filtros de fechas y estado.
