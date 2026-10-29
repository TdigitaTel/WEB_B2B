# El cliente elige el precio destacado

La cuenta principal del cliente configura **Mi cuenta → Preferencias → Precios del catálogo**:

- Con IVA destacado · sin IVA más pequeño (valor por defecto).
- Sin IVA destacado · con IVA más pequeño.

Al guardar se actualizan las tarjetas de catálogo y favoritos ya cargadas y se limpian las sugerencias antiguas. Los subusuarios heredan la elección al cargar productos; pueden consultar el valor en Preferencias si tienen acceso a esa pestaña, pero no cambiar la preferencia común. El operador no tiene selector ni API de gestión de este parámetro.

La tarjeta conserva ambos importes recibidos de EXIT. Las sugerencias muestran el importe elegido y su etiqueta; la ordenación usa el importe destacado. No se cambian descuentos, cálculos de IVA, carrito, pedidos ni documentos por esta preferencia.

## API y permisos

- GET `/api/v1/account/catalog-price`: lee la preferencia del cliente asociado a la sesión.
- PATCH al mismo endpoint: `{"highlight_price_without_tax":true}`. Solo cuenta principal de cliente con permiso de preferencias.

No acepta `customer_code` ni otros campos, ni permite elegir otro cliente. Los operadores reciben 403 y los subusuarios no pueden escribir aunque tengan permiso para sus preferencias personales. Se retiran GET/POST de `/api/v1/store/customer-access/catalog-price`.

Se conserva `customer_catalog_settings`, clave `customer_code`; sin fila equivale a destacar con IVA. Se mantienen valores que pudieran estar guardados. El bootstrap crea la tabla, sin SQL manual. Se audita el cambio con el usuario cliente que lo realiza y se serializan escrituras por cliente en PostgreSQL. No se escribe en EXIT.

## Validación

Pruebas de guardado por el propio cliente, aislamiento entre clientes y rechazo de campos ajenos, permiso de preferencias, rechazo a operadores, retiro del endpoint de gestión, herencia y bloqueo de escritura de subusuarios, valores existentes, precios ocultos y uso en catálogo, detalle, favoritos y sugerencias. Pantalla y guardado comprobados con una sesión local de cliente y datos de ejemplo. Pendiente verificar con el cliente real tras integrar y desplegar en desarrollo.
