# Recogida de pedidos

El cliente elige Inmediata (fecha nula) o Programada (fecha desde mañana, calendario Europe/Madrid del servidor). La API también valida el mínimo. La fecha se guarda en orders.pickup_date y se devuelve en las consultas WEB e integración.

En Parámetros, el operador configura los minutos estimados de preparación inmediata. Valor inicial: 60 minutos; configurable entre 1 y 10080. Se almacena en pickup_settings y se audita cada cambio.

El arranque crea pickup_settings y añade orders.pickup_date de forma idempotente. No requiere borrar datos.

El aviso indica conservación de 24 horas desde la preparación. Este cambio añade el aviso comercial, no un proceso de eliminación automática ni eliminación de registros históricos.
