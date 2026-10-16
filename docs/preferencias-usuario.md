# Preferencias de visualización del usuario

En Mi cuenta se mantienen los datos de usuario y cliente como información de solo lectura y el formulario de cambio de contraseña. La sección Preferencias de visualización permite guardar dos opciones independientes:

- Miniaturas en albaranes: muestra una fotografía pequeña junto a cada material del detalle del albarán.
- Miniaturas en pedidos: muestra una fotografía pequeña junto a cada material de Mis pedidos.

Ambas están desactivadas por defecto (solo texto). Las preferencias pertenecen a la cuenta y se conservan entre sesiones. No ocultan pedidos ni albaranes; controlan únicamente sus imágenes. Guardar preferencias no modifica datos comerciales de EXIT.

Las miniaturas se obtienen de la imagen existente del producto por SKU, con la misma autenticación y origen de imágenes del catálogo. Se cargan de forma diferida. Si la imagen o el producto no está disponible, el detalle conserva el texto y muestra un marcador discreto.

API autenticada:

```text
PATCH /api/v1/account/preferences
{"show_delivery_note_images":true,"show_order_images":false}
```

La respuesta de login y GET /api/v1/account incluye ambos valores. El usuario solo puede modificar sus propias preferencias; no se aceptan campos de identidad en este endpoint.

El bootstrap añade automáticamente a users las columnas booleanas show_delivery_note_images y show_order_images, ambas NOT NULL con valor inicial false. No es necesario migrar datos comerciales ni copiar preferencias entre ambientes.
