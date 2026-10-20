# Recogida de pedidos

El cliente elige Inmediata (fecha nula) o Programada (fecha desde mañana, calendario Europe/Madrid del servidor). La API también valida el mínimo. La fecha se guarda en orders.pickup_date y se devuelve en las consultas WEB e integración.

En Parámetros, el operador configura los minutos estimados de preparación inmediata. Valor inicial: 60 minutos; configurable entre 1 y 10080. Se almacena en pickup_settings y se audita cada cambio.

El arranque crea pickup_settings y añade orders.pickup_date de forma idempotente. No requiere borrar datos.

El aviso indica conservación de 24 horas desde la preparación. Este cambio añade el aviso comercial, no un proceso de eliminación automática ni eliminación de registros históricos.

## Horarios por sede

En Parámetros se edita por sede el horario semanal: apertura/cierre de mañana y tarde, lunes a domingo. Turno vacío = cerrado. No se admiten turnos incompletos, invertidos o solapados. Se identifican las sedes por empresa y delegación de EXIT.

La recogida inmediata se ofrece si la preparación cabe hoy en el turno actual o en el siguiente. En una pausa, la preparación empieza al abrir el próximo turno y el carrito muestra la hora estimada de recogida. Los turnos consecutivos sin pausa se unen. La igualdad con el cierre sí es válida. Se usa la hora del servidor Europe/Madrid. Una sede sin horario configurado solo ofrece recogida programada. No incluye calendario de festivos.

El carrito consulta disponibilidad por sede cada 30 segundos y al cambiar de sede. La API comprueba de nuevo al enviar el pedido o un borrador. Si inmediata no está disponible, se oculta y se selecciona programada.

El arranque añade pickup_settings.schedules JSON de forma idempotente. Deben configurarse los horarios reales de las cinco sedes después de desplegar; no se inventan horarios iniciales.

La fecha programada mínima se calcula como el siguiente día con algún turno abierto en la sede, desde mañana. Salta fines de semana u otros días semanales cerrados; sin turnos configurados no propone fecha. La API rechaza programaciones en días cerrados. Ejemplo: viernes 18:01 + 60 minutos, cierre 19:00 y fin de semana cerrado -> lunes.

## Excepción del operador

Pedidos WEB muestra Recogida: Inmediata o Programada y su fecha. Cambiar recogida permite al operador atender un pedido como inmediato aunque exceda el horario. El cliente no puede usar esta excepción. Cambiar a programada exige una fecha futura abierta. No se modifica un pedido entregado/facturado. Cada modificación se registra con actor, fecha y valores anterior/nuevo en auditoría e historial.

Cada día tiene un check Con atención. Desmarcarlo cierra el día sin perder las horas guardadas. Un día marcado pero sin ningún turno completo también se considera cerrado. Los horarios anteriores con horas se mantienen abiertos por compatibilidad.


Ejemplo de mediodía: pedido a las 13:00, 60 minutos de preparación y tarde 16:00–19:00 -> inmediata para hoy con recogida estimada 17:00. Si la tarde abre 13:00, recogida estimada 14:00. Después de 18:00 con cierre 19:00 y preparación de 60 minutos -> siguiente día hábil. Esta corrección no cambia automáticamente pedidos ya creados; el operador puede usar Cambiar recogida.
