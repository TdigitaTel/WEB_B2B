# Precio destacado por cliente

En **Accesos de clientes**, seleccionar un cliente de EXIT y abrir **Precios del catálogo**:

- Con IVA destacado · sin IVA más pequeño (valor por defecto).
- Sin IVA destacado · con IVA más pequeño.

Guardar afecta al cliente y a todos sus subusuarios. Se aplica cuando se vuelven a cargar productos; refrescar la web para renovar también las tarjetas ya cargadas. No requiere cerrar sesiones.

La misma tarjeta se usa en catálogo y favoritos. Las sugerencias muestran el importe elegido y su etiqueta con/sin IVA. La ordenación por precio utiliza el importe destacado. Ambos importes conservan los valores recibidos de EXIT; no se calculan impuestos ni se cambian descuentos, pedidos, carrito o documentos por esta preferencia.

## Persistencia y API

Tabla complementaria `customer_catalog_settings`, con `customer_code` como clave, booleano `highlight_price_without_tax` y fechas. Una fila por cliente EXIT, compartida por sus cuentas y subusuarios. Sin fila equivale a `false` (resaltar con IVA). El bootstrap existente crea la tabla; no se necesita SQL manual.

- GET `/api/v1/store/customer-access/catalog-price?customer_code=00004`
- POST `/api/v1/store/customer-access/catalog-price` con `{"customer_code":"00004","highlight_price_without_tax":true}`.

Ambos endpoints requieren operador/administrador con permiso de Accesos de clientes y verifican que el cliente existe en EXIT. Se registra auditoría. En PostgreSQL un bloqueo por cliente serializa los primeros guardados y las actualizaciones. No se escribe en EXIT.

El catálogo, detalle y favoritos devuelven la preferencia junto a los dos precios. Sugerencias conserva el campo `price` con el importe destacado y añade `price_includes_tax`. Los permisos existentes siguen ocultando todos los importes cuando el usuario no puede ver precios.

## Validación

Pruebas de valor por defecto, guardado, cambio de vuelta, importes sin cambios, detalle, favoritos, sugerencias y etiquetas, subusuarios, ocultación de precios, permisos de módulo y cliente inválido. Pantalla revisada y guardado comprobado en navegador con datos locales de ejemplo. Pendiente verificar con clientes y precios reales de EXIT tras desplegar en desarrollo.
