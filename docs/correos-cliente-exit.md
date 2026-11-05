# Contactos de EXIT y avisos de pedidos

La ficha consulta `dbo.Clientes` al leer Mi cuenta y mediante **Actualizar desde EXIT**. `Email1` ya era el origen del contacto principal: este cambio lo identifica por su nombre y añade `Email2` y `Web`. No cambia el correo con el que se inicia sesión ni escribe en SQL Server. Si el valor de Email1 continúa siendo diferente del de una consulta externa, verificar que desarrollo y producción apuntan a la misma base/servidor EXIT esperado; no se ha confirmado esa configuración remota desde este entorno.

- **Email1 y Email2:** datos de EXIT, cada uno con **Recibir avisos de estado**. Las marcas son del cliente ERP (incluidos ceros iniciales), no del usuario de acceso. Solo la cuenta principal con permiso de preferencias puede modificarlas. Los subusuarios pueden consultarlas.
- **Web:** texto de referencia. Nunca es un destinatario ni un indicador de envío.
- **Correo de acceso:** sigue siendo independiente; no se añade como destino alternativo.
- Las marcas inicialmente están desactivadas. Se conserva la selección por campo: cambiar Email1 en EXIT cambia el destinatario del campo marcado. Campos vacíos o inválidos no reciben mensajes; al guardar no se pueden activar campos inválidos. Direcciones repetidas se envían una sola vez, cada destino por separado y sin CC.

## Activación

1. Integrar esta rama y desplegar. El arranque habitual de la API (`app.bootstrap`) crea tres tablas nuevas de PostgreSQL mediante `create_all`: `customer_order_email_settings`, `order_email_checkpoints` y `order_email_deliveries`. No modifica ni elimina datos de clientes/pedidos existentes.
2. El despliegue de Compose añade `order-email-worker`, reutilizando la imagen API y su entorno privado, incluida la misma clave de cifrado SMTP. No expone puertos ni requiere otra contraseña.
3. En **Mi cuenta → Mis datos**, marcar y guardar los correos deseados.
4. En **Parámetros → Correo de pedidos**, revisar cuenta SMTP y estados y activar **Avisos automáticos de cambios de estado**. El interruptor general empieza desactivado, aunque exista una cuenta SMTP configurada. La prueba manual continúa independiente.

La configuración, marcas y cola son independientes en las bases de desarrollo y producción. El SMTP aún puede rechazar el envío por credenciales o políticas del proveedor: configurar destinos no elimina esos requisitos.

## Qué dispara los avisos

La API registra en la misma transacción los cambios visibles de pedidos WEB, incluidos los derivados de sincronizar líneas/albaranes EXIT y de confirmar recogidas. Se conserva una revisión por pedido y se crea una salida por cambio seleccionado, con contenido configurable y resumen de materiales. Las modificaciones de notas sin cambio de estado no generan avisos. Borradores y pedidos eliminados físicamente no reciben mensajes.

El trabajador revisa la cola cada diez segundos, consulta los **correos vigentes de EXIT al enviar** y vuelve a comprobar las marcas. No usa copias antiguas del correo ni el correo del login. Los estados de pedidos EXIT se actualizan mediante los mecanismos de sincronización/gestión existentes: este trabajador envía avisos, no constituye un nuevo sincronizador periódico de pedidos EXIT. Una modificación en EXIT se notificará cuando la extranet la sincronice y confirme.

Al activar/reactivar se toma el estado actual como punto de partida y se cancelan salidas pendientes anteriores: no se reproducen históricos. Una salida pendiente de un estado superado se descarta. Al incluir enlace se genera un seguimiento de solo lectura de 30 días; el secreto se guarda cifrado en la cola y únicamente como hash en la tabla de enlaces, sin revocar los enlaces compartidos manualmente.

## Comprobación en el servidor

Usar los mismos archivos Compose y `.env` privados del despliegue. Los nombres habituales de proyecto son `webb2b-dev` y `web_b2b`:

```bash
docker ps --filter name=order-email-worker --format 'table {{.Names}}\t{{.Status}}'
docker logs --since 30m webb2b-dev-order-email-worker-1
docker logs --since 30m web_b2b-order-email-worker-1
```

Los registros `ORDER_EMAIL_SENT` confirman aceptación SMTP, no entrega final en la bandeja. `ORDER_EMAIL_FAILED` incluye fase, clase de excepción, código y respuesta sanitizada, sin direcciones ni credenciales. La cola guarda `SENT`, `CANCELLED`, `SUPERSEDED`, `NO_RECIPIENT`, `RETRY`, `FAILED` o `UNCERTAIN`.

Los fallos previos al envío se reintentan hasta cinco veces con espera creciente. Los destinatarios ya aceptados no se repiten. Un corte durante la fase de envío o un reinicio con una salida `SENDING` produce `UNCERTAIN`, sin repetición automática: se debe comprobar el seguimiento del proveedor antes de cualquier reenvío manual. Un bloqueo de PostgreSQL impide dos trabajadores enviando a la vez. Las pruebas usan una base desechable y transporte simulado; no se han enviado correos reales.
