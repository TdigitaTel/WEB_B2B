# Refresco automático sin parpadeos

El intervalo global de actualización se mantiene. La carga inicial y las consultas manuales siguen dando información de progreso; las consultas periódicas actualizan en segundo plano sin cambiar el texto ni la opacidad de los botones.

- Pedidos del cliente: el refresco periódico usa `background=true`. Una respuesta antigua no sustituye la de una consulta más reciente, y las respuestas anteriores al cierre de sesión se descartan.
- Operador: el refresco automático conserva los controles y los detalles abiertos. El aviso de error se conserva durante el siguiente intento y se retira cuando llega una respuesta correcta, evitando que desaparezca y reaparezca en cada intento fallido.
- Previsiones por línea: «Cargando…» se usa en la carga inicial. Durante consultas posteriores se mantienen las celdas anteriores, incluso si la consulta previa devolvió una lista vacía. Los resultados idénticos no actualizan el estado de presentación.

No se ocultan cambios reales de estado ni se demora su publicación con animaciones. Las consultas lentas no se solapan dentro de la misma suscripción y se respetan los filtros aplicados, el intervalo configurado y las pausas de edición existentes.

Validación: pruebas React con respuestas retenidas para comprobar el estado durante la petición, etiqueta/opacidad de los controles, permanencia del mismo nodo de detalle abierto, modo silencioso del cliente y celdas de planificación vacías. Compilación de producción y pruebas de planificación relacionadas.
