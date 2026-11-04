# Correo de pedidos

En **Parámetros → Correo de pedidos** se guardan nombre y correo del remitente, dirección de respuesta, servidor SMTP, puerto, modo STARTTLS o SSL, usuario, contraseña, URL pública HTTPS y estados visibles para el cliente que se desean notificar. El remitente inicial es **info@bermudezulloa.es**. El proveedor debe confirmar servidor, puerto, seguridad y método de autorización. No se admite transporte sin cifrado. Si requiere OAuth, esta primera configuración SMTP con contraseña de aplicación no sustituye esa integración.

La credencial se cifra con Fernet usando una clave derivada con dominio propio del secreto JWT existente. No se devuelve al navegador ni se incluye en auditoría. Una contraseña vacía conserva la guardada; existe eliminación explícita. Debe conservarse el secreto del servidor entre despliegues; si cambia, hay que guardar de nuevo la credencial. No se alteran los parámetros SMTP de los correos de acceso existentes.

API (operador/administrador con permiso de Parámetros): GET y PUT `/api/v1/store/order-email-settings`; POST `/api/v1/store/order-email-settings/test` con `recipient`. La prueba usa exclusivamente la configuración guardada, un destinatario explícito y límites de espera; no consulta ni envía pedidos. SMTP aceptado no garantiza llegada a bandeja: revisar también correo no deseado. No hay pruebas reales de correo realizadas por el desarrollo.

## Alcance de esta interfaz

Se preparan y persisten los parámetros, preferencias de estados y prueba manual. **El envío automático por cambios de estado no está conectado en esta revisión.** La API devuelve `automatic_dispatch_available=false` y la pantalla lo indica; no existe un interruptor que prometa activarlo. La tabla nueva se crea mediante el bootstrap habitual, sin migración manual.

Para conectar el envío automático se necesita un servicio de eventos y cola persistente por pedido y transición visible al cliente, con historial, destinatarios deduplicados de su ficha, reintentos y prevención de duplicados entre refrescos. El estado de preparación por albarán y la recogida física deben conservarse separados. La activación debe partir del estado actual para evitar un envío masivo de estados históricos. Los fallos de correo no deben impedir registrar ni atender el pedido.

## Mensajes según el estado

`order_status_email.py` genera HTML con estilos en línea y alternativa de texto, partiendo de los campos públicos de seguimiento. Incluye pedido, estado, una frase de acción, avance de recogida por materiales, fecha relevante y botón de seguimiento; no incluye precios, observaciones internas ni datos fiscales. La facturación no sustituye el estado físico de recogida. Sin desglose fiable no inventa porcentajes. El detalle de artículos queda en la web.

En Parámetros, «Contenido del correo» permite seleccionar estado y abrir una vista previa aislada. GET `/api/v1/store/order-email-settings/preview?state=ENTREGADO_PARCIAL` devuelve asunto, HTML y texto con datos ficticios. POST `/test` admite `preview_state` (por defecto ENTREGADO_PARCIAL) y envía la misma plantilla, marcada PRUEBA y con enlace a la entrada de la extranet. No crea pedidos ni enlaces privados. La generación real de enlaces y el despachador automático siguen pendientes de integración, como indica la pantalla.
