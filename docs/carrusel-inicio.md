# Carrusel de imágenes del inicio

Pantalla del operador: **Parámetros → Imágenes del inicio**, con permiso de Parámetros. De 1 a 10 imágenes, carga JPG/PNG/WebP, sustitución individual, orden y retirada conservando al menos una. Archivos de hasta 8 MB y 20 megapíxeles, optimizados en navegador a 800 KiB antes de subir y convertidos a WebP en el servidor.

Al principio usa la imagen actual de acceso, o el logotipo incluido si no hay una imagen configurada. Al personalizar por primera vez se conserva una copia de la imagen de acceso como primera imagen, independiente de futuros cambios del acceso. Añadir incorpora otra al final; sustituir cambia solo la seleccionada. No se modifica `login_appearance`.

El bloque anterior de bienvenida se sustituye por la imagen con solo **Explorar catálogo**. Con varias imágenes cambia cada 5 segundos; con una no rota. Se pausa con puntero/foco, con la pestaña oculta y con preferencia de reducir movimiento. Se eliminan el saludo, título, pasos y texto lateral superpuestos. No se añade capa oscura.

En ordenador se adapta a un banner de 240 a 420 px de alto y puede recortarse. En móvil se ve completa, con proporción natural y todo el ancho, y un botón de al menos 44 px. Conviene preparar imágenes con la misma proporción para mantener estable la altura durante la rotación.

## Persistencia y API

Tablas nuevas `home_carousel_settings` (revisión de la lista) y `home_carousel_images` (imagen, posición y revisión). El bootstrap habitual las crea; no hay SQL manual ni cambios de Docker. Las escrituras se serializan por configuración en PostgreSQL y exigen revisión vigente para evitar sobrescribir cambios de otro operador. Todos los accesos necesitan sesión; las modificaciones requieren permiso de Parámetros.

- `GET /api/v1/home-carousel`: revisión, imágenes ordenadas y `interval_seconds: 5`.
- `GET /api/v1/home-carousel/images/{id}`: imagen privada con sesión.
- `POST /api/v1/home-carousel`: multipart `file`, `revision` y opcional `replace_id`; sin ese campo añade una imagen.
- `PATCH /api/v1/home-carousel`: `revision` y `image_ids` con la lista completa en el orden deseado.
- `DELETE /api/v1/home-carousel/images/{id}?revision=...`: retira una imagen si quedan más.

409 indica una lista desactualizada: actualizar antes de reintentar. La configuración no afecta a EXIT ni genera pedidos. Los cambios se ven al volver a cargar el inicio.

## Validación

262 pruebas del API correctas en base desechable, incluyendo imagen inicial, copia independiente, sesiones/permisos, orden, sustitución, revisión, límite de 10, mínimo de una y formatos inválidos. Compilación y TypeScript correctos. Navegador con gráficos de ejemplo: rotación, solo botón sobre el gráfico, apertura del catálogo y ancho completo en 320 y 390 px; configuración sin desbordamiento en 320 px. Pendiente comprobar la imagen real y la persistencia de PostgreSQL tras desplegar en desarrollo.
