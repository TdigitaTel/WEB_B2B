# Banner de inicio

El operador y el administrador gestionan el banner desde **Parámetros → Web → Banner de inicio**.

- Se conserva el diseño original como diapositiva inicial, con el saludo del cliente conectado. El botón «Explorar catálogo» es independiente y se superpone a todas las imágenes.
- Se pueden añadir varias imágenes a la vez, ordenarlas, activar/desactivar y eliminar las personalizadas. No hay un número máximo de diapositivas configurado. Cada archivo admite JPG, PNG o WebP, hasta 8 MB y 20 megapíxeles; se optimiza antes de subir y se almacena como WebP.
- Formato recomendado: 2400 × 480 px. Las imágenes se muestran completas, sin recortar; dejar libre la esquina inferior izquierda para el botón y la zona inferior central para los puntos. En móvil la imagen completa se ajusta dentro del banner.
- Tiempo de rotación configurable entre 3 y 120 segundos, inicialmente 5. Los intervalos ya guardados se conservan; se pueden cambiar en «Segundos por imagen». Un punto centrado por imagen activa permite elegirla e indica cuál se está mostrando. El avance automático continúa con el ratón o el foco dentro del banner; se detiene mediante el botón discreto de pausa o al ocultar la pestaña. Se respeta la preferencia de movimiento reducido.
- Guardar aplica orden, visibilidad, descripciones y tiempo; añadir/eliminar imágenes se guarda inmediatamente. Guardar los cambios pendientes antes de añadir/eliminar. Si otro operador ha cambiado la configuración se muestra un conflicto en lugar de sobrescribirlo.
- Al abrir o recargar Inicio se lee la configuración. No añade consultas periódicas al servidor. Sin imágenes activas, ante un error de carga o sin configuración se conserva el diseño original y su acceso al catálogo.

Las tablas `home_banner_settings` y `home_banner_slides` se crean automáticamente mediante el arranque habitual (`Base.metadata.create_all`). Las imágenes se guardan en PostgreSQL y entran en su copia de seguridad; no requieren carpetas o volúmenes nuevos. Desarrollo y producción conservan sus propias imágenes y configuración.

La configuración devuelve únicamente metadatos. Los bytes se descargan individualmente al mostrar la imagen; las previsualizaciones del operador usan una ruta autenticada para poder ver también imágenes desactivadas. Las modificaciones están auditadas.
