# Subida de imagen de acceso

El error `Unexpected token '<' ... is not valid JSON` aparece cuando la pantalla intenta interpretar una respuesta HTML del servidor como JSON. La captura no identifica el estado HTTP original ni confirma su causa; una hipótesis compatible es un rechazo de tamaño por el proxy, cuyo límite no está versionado en este repositorio.

## Corrección

La pantalla conserva el límite de selección de 8 MB y de 20 megapíxeles. Antes de enviar, valida el archivo y prepara una versión de hasta 800 KiB: limita la dimensión mayor a 2400 píxeles y, si es necesario, reduce calidad y dimensiones. Conserva la relación de aspecto y libera las URL temporales. El margen restante permite el formulario multipart bajo un límite de proxy de 1 MiB. Las imágenes pequeñas que ya cumplen el límite no se recomprimen en el navegador.

Muestra «Preparando imagen…» y después «Guardando…». Una selección inválida limpia el archivo anterior para evitar guardar otra imagen por error. El API mantiene su validación y conversión actuales.

El tratamiento de respuestas tolera cuerpos HTML o inválidos y presenta mensajes de tamaño (413), sesión (401), permisos (403), servicio no disponible (502/503/504) o error general. Solo confirma el guardado cuando recibe la estructura válida de configuración. La restauración usa el mismo tratamiento.

## Validación

- `npm run test:login-image`: HTML/JSON, errores, confirmación, formatos y tamaño, optimización progresiva, megapíxeles, errores de decodificación y limpieza.
- Pruebas existentes del API de imagen: subida, lectura pública, permisos, restauración y límite de tamaño.
- Compilación web y TypeScript.
- Prueba real en Chrome con imagen sintética PNG de 7.211.364 bytes y proxy local de 1 MiB: original sin optimizar → HTTP 413 con HTML; subida desde la pantalla corregida → petición multipart de 736.050 bytes, HTTP 200 y lectura de imagen guardada HTTP 200.

Los servicios locales y archivos de ejemplo no se incluyen en el cambio. No se modificó la imagen ni la configuración de desarrollo o producción. Tras desplegar, probar el archivo original en ambos entornos; si persiste un rechazo, revisar el estado HTTP y los registros del proxy/API. No se necesita un cambio de base de datos.
