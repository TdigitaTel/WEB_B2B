# Recogida de pedidos

El cliente elige Inmediata (fecha nula) o Programada (fecha desde mañana, calendario Europe/Madrid del servidor). La API también valida el mínimo. La fecha se guarda en orders.pickup_date y se devuelve en las consultas WEB e integración.

En Parámetros, el operador configura los minutos estimados de preparación inmediata. Valor inicial: 60 minutos; configurable entre 1 y 10080. Se almacena en pickup_settings y se audita cada cambio.

El arranque crea pickup_settings y añade orders.pickup_date de forma idempotente. No requiere borrar datos.

El aviso indica conservación de 24 horas desde la preparación. Este cambio añade el aviso comercial, no un proceso de eliminación automática ni eliminación de registros históricos.

## Horarios por sede

En Parámetros se edita por sede el horario semanal: apertura/cierre de mañana y tarde, lunes a domingo. Turno vacío = cerrado. No se admiten turnos incompletos, invertidos o solapados. Se identifican las sedes por empresa y delegación de EXIT.

La recogida inmediata requiere que la hora actual del servidor (Europe/Madrid) esté dentro de un turno y que, al sumar los minutos de preparación, no supere su cierre. La igualdad con el cierre sí es válida. No se trasladan minutos al turno siguiente. Una sede sin horario configurado solo ofrece recogida programada. No incluye calendario de festivos.

El carrito consulta disponibilidad por sede cada 30 segundos y al cambiar de sede. La API comprueba de nuevo al enviar el pedido o un borrador. Si inmediata no está disponible, se oculta y se selecciona programada.

El arranque añade pickup_settings.schedules JSON de forma idempotente. Deben configurarse los horarios reales de las cinco sedes después de desplegar; no se inventan horarios iniciales.
