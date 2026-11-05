# Microfotos en Pedidos WEB del operador

La opción «Mostrar microfotos» está en la barra del gestor, solo en la pestaña
Pedidos WEB. Guarda la preferencia `users.show_order_images` del operador mediante
el endpoint existente `/api/v1/account/preferences`; mantiene el valor de
`show_delivery_note_images`. Persiste al volver a entrar y no cambia preferencias
de clientes ni activa imágenes en Kardex, SGA, Atendidos, catálogo o albaranes.

Las imágenes usan el componente existente de miniaturas por SKU, con carga
diferida y sustitución por familia cuando no existe imagen. Si guardar falla,
se informa y se conserva la preferencia previa. El refresco no la reinicia.
No hay migración ni dependencias nuevas.

Esta rama incorpora también la corrección pendiente 808bba9: `created_in_web=true`
muestra WEB, y cualquier otro valor muestra Tienda con el check vacío. Esa
corrección anterior no se había integrado en develop/main, por eso la pantalla
publicada seguía mostrando «Sin confirmar».

Comprobaciones: persistencia y aislamiento de preferencias del operador en API;
`node scripts/test-operator-order-images.cjs`, pruebas de conservación de líneas,
seguimiento, refresco y compilación.
