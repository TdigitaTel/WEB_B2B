# Fecha y hora límite de atención

Cada pedido WEB enviado conserva:

- `attention_deadline_at`: fecha y hora máxima prevista para su atención, almacenada con zona horaria en PostgreSQL.
- `preparation_minutes_snapshot`: minutos de preparación utilizados en ese cálculo.

La web presenta las horas en Europe/Madrid. El servidor calcula y valida los valores: no acepta un plazo enviado por el navegador.

**Inmediata:** hora del servidor más el parámetro de preparación. Si todavía no ha abierto la sede o hay una pausa entre turnos, se usa la siguiente apertura disponible de ese día más la preparación. Se mantienen las reglas existentes que impiden ofrecer inmediata cuando no cabe dentro del horario de atención.

**Programada:** apertura de la mañana del día elegido más el mismo parámetro de preparación. Por ejemplo, apertura a las 08:00 y parámetro 60 minutos: límite a las 09:00 de ese día. Si la sede solo tiene turno de tarde, se utiliza su primera apertura disponible. Se rechaza una fecha sin un turno que permita completar la preparación.

El carrito consulta la previsión para la sede y fecha elegidas. Al enviar el pedido, el servidor vuelve a calcular y guarda el compromiso definitivo. Los borradores reciben el plazo al enviarse, no cuando se guardan como borrador.

Cambiar los parámetros de la sede no modifica los plazos ya guardados. Si el operador cambia la recogida, se calcula un nuevo plazo con los parámetros vigentes y se registra el cambio en el histórico y la auditoría. La excepción del operador para convertir en inmediata fuera del horario habitual conserva su funcionamiento: se calcula desde ese momento más los minutos configurados.

El plazo aparece en confirmación, detalle del cliente y ventana Pedidos WEB del operador; la API de integración también lo incluye al consultar el pedido. Es un dato de seguimiento: no cierra ni elimina automáticamente pedidos, y no cambia la regla de conservación durante 24 horas.

## Publicación

La actualización idempotente de `app.bootstrap` añade las dos columnas y un índice sobre `attention_deadline_at`. Actualizar API y frontend conjuntamente. No se inventan plazos históricos para pedidos anteriores: aparecen como «Sin plazo registrado» hasta que se modifique su recogida. No se modifican tablas de EXIT.
