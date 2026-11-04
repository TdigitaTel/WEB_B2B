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

Prueba de la vista previa: `node frontend/scripts/test-order-email-preview.cjs`. No se añaden entradas al manifiesto para mantener independiente esta mejora de otros menús y pantallas.

## Contenido configurable

El editor separa «Qué quieres decir», «Qué información incluir» y la vista previa.
Se pueden cambiar inicio del asunto, saludo, mensaje por estado, despedida,
condiciones y texto del botón. Los textos sugeridos se pueden recuperar para un
estado sin sustituir los demás. Un texto vacío se omite; todo se trata como texto
simple y se escapa al generar HTML.

Se elige mostrar avance, fechas, número de tienda, materiales, cantidades,
condiciones y enlace directo. Si se desactiva el enlace no se incluye ninguna URL
en ninguna versión del correo. Los materiales se obtienen del mismo contenido
público autorizado del seguimiento: no se exponen precios ni notas internas.
Se conservan las líneas eliminadas con su marca; se muestran como máximo 50 y
se avisa si hay más.

La configuración se almacena en `order_email_settings.configuration.content`
(JSON existente; sin migración). La vista previa `POST /preview` recibe solo
`state` y `content`, está protegida para operadores, no guarda ni envía mensajes.
El correo de prueba usa la configuración guardada. La conexión SMTP se conserva
en una sección desplegable; no se envían sus credenciales a la vista previa.
El envío automático por cambios de estado sigue pendiente de conectar.

## Diagnóstico del correo de prueba

El error de la prueba incluye fase (CONNECT/TLS/AUTH/SEND), clase de excepción de
`smtplib`, código SMTP cuando existe y respuesta recibida del servidor. Una
referencia permite encontrarlo en los registros de la API y en `audit_events`
(acción `ORDER_EMAIL_TEST_FAILED`, `metadata_json`). Se ocultan credenciales,
representaciones de autenticación en base64 y direcciones de correo, y se limita
la longitud de la respuesta. No se activa `set_debuglevel`: una transcripción
SMTP completa podría registrar las credenciales de AUTH.

Los fallos anteriores al cambio solo guardaban la marca de error, sin respuesta;
no se puede recuperar retrospectivamente el detalle. Hay que repetir la prueba
tras desplegar. El diagnóstico no cambia la configuración de Microsoft 365 ni
confirma por sí solo que una contraseña sea incorrecta. La cuenta puede exigir
OAuth o tener restricciones de autenticación/envío.
