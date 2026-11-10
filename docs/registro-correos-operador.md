# Registro de correos del pedido

En Operaciones, desplegar el pedido WEB y pulsar **Correo y registro**. El diálogo conserva el reenvío manual y añade el historial, actualizado mediante consultas de lectura mientras está abierto.

Se muestran fecha y estado, resultado (en cola, enviando, aceptado por SMTP, error/reintento, error definitivo, resultado incierto, cancelado, sustituido o sin destinatarios), intentos, próxima fecha de reintento y destinos aceptados (Email1/Email2). En el detalle de eventos se conservan los errores anteriores aunque un reintento termine bien: fase, excepción de librería, código SMTP, respuesta sanitizada y referencia.

La biblioteca no devuelve el texto de confirmación SMTP en los envíos exitosos. Se registra la aceptación sin destinatarios rechazados; no se inventa un código 250 ni se confirma recepción en bandeja. No se guardan contraseñas, contenido de mensajes, direcciones ni tokens de seguimiento en este registro.

Los cambios de estado sin aviso por selección de estados, automatismo desactivado o ausencia de destinatarios marcados dejan un evento de aviso no generado. Activar la función no envía correos históricos. Consultar el registro nunca genera ni reenvía correos.

La consulta independiente `GET /api/v1/store/orders/{order_id}/email/history` conserva el permiso y el ámbito del pedido. No consulta EXIT ni SMTP; permite ver el registro aunque fallen. Devuelve hasta 50 avisos y 200 eventos recientes por defecto (límite máximo 100 avisos/400 eventos). Se almacena en la auditoría existente: no requiere una migración de tablas. Los envíos anteriores conservan su último resultado, pero no es posible reconstruir errores anteriores que ya se sobrescribieron.
