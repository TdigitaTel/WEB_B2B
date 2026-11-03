# Correo de pedidos

En **Parámetros → Correo de pedidos** se guardan nombre y correo del remitente, dirección de respuesta, servidor SMTP, puerto, modo STARTTLS o SSL, usuario, contraseña, URL pública HTTPS y estados visibles para el cliente que se desean notificar. El remitente inicial es **info@bermudezulloa.es**. El proveedor debe confirmar servidor, puerto, seguridad y método de autorización. No se admite transporte sin cifrado. Si requiere OAuth, esta primera configuración SMTP con contraseña de aplicación no sustituye esa integración.

La credencial se cifra con Fernet usando una clave derivada con dominio propio del secreto JWT existente. No se devuelve al navegador ni se incluye en auditoría. Una contraseña vacía conserva la guardada; existe eliminación explícita. Debe conservarse el secreto del servidor entre despliegues; si cambia, hay que guardar de nuevo la credencial. No se alteran los parámetros SMTP de los correos de acceso existentes.

API (operador/administrador con permiso de Parámetros): GET y PUT `/api/v1/store/order-email-settings`; POST `/api/v1/store/order-email-settings/test` con `recipient`. La prueba usa exclusivamente la configuración guardada, un destinatario explícito y límites de espera; no consulta ni envía pedidos. SMTP aceptado no garantiza llegada a bandeja: revisar también correo no deseado. No hay pruebas reales de correo realizadas por el desarrollo.

## Alcance de esta interfaz

Se preparan y persisten los parámetros, preferencias de estados y prueba manual. **El envío automático por cambios de estado no está conectado en esta revisión.** La API devuelve `automatic_dispatch_available=false` y la pantalla lo indica; no existe un interruptor que prometa activarlo. La tabla nueva se crea mediante el bootstrap habitual, sin migración manual.

Para conectar el envío automático se necesita un servicio de eventos y cola persistente por pedido y transición visible al cliente, con historial, destinatarios deduplicados de su ficha, reintentos y prevención de duplicados entre refrescos. El estado de preparación por albarán y la recogida física deben conservarse separados. La activación debe partir del estado actual para evitar un envío masivo de estados históricos. Los fallos de correo no deben impedir registrar ni atender el pedido.
