# Actualización automática de pantallas

Operador → Parámetros → Actualización de pantallas. Intervalo global por ambiente, guardado en PostgreSQL en `screen_refresh_settings` (fila 1). Predeterminado 5 segundos; entero entre 5 y 300. `bootstrap` crea la tabla automáticamente, sin tareas programadas ni cambios en Linux.

- GET `/api/v1/screen-refresh-settings`: solo devuelve el intervalo, sin datos del negocio. También lo usa la imagen de acceso.
- PATCH `/api/v1/store/screen-refresh-settings`: operadores y administradores; clientes y visitantes no pueden modificarlo. Ejemplo: `{"interval_seconds": 5}`. El cambio queda auditado.
- Las otras sesiones abiertas adoptan el cambio en su siguiente consulta del parámetro (hasta 5 segundos con la pestaña visible). Una sesión que guarda lo consulta inmediatamente.

Se actualiza la vista activa: Kardex, Atendidos, SGA, Pedidos WEB, Mis pedidos, resumen del inicio, favoritos, catálogo, documentos, albarán abierto y planificación visible de líneas. También las listas de accesos, subusuarios, categorías, marcas, sinónimos y series; los parámetros y preferencias se consultan solo si no hay edición pendiente. Los paneles de configuración ocultos no consultan sus listas.

Se mantiene la última consulta aplicada: modificar una fecha, estado o delegación no aplica ese filtro hasta pulsar Consultar. No se recarga la página ni se cambian los identificadores de los detalles abiertos. Los errores transitorios conservan los últimos datos; Operaciones muestra el error y vuelve a intentarlo.

El planificador impide solapar sus consultas, cancela al desmontar/cambiar consulta, pausa la pestaña oculta o sin conexión y espera mientras se escribe (1,5 segundos desde la última entrada). Los formularios con cambios sin guardar conservan sus valores. El resumen de inicio conserva también su propia protección de peticiones pendientes. Las lecturas simultáneas idénticas de la página principal comparten la petición cuando no tienen un controlador de cancelación propio, sin guardar una caché de respuestas.

La reposición consulta trabajos y resultados guardados; no inicia nuevos cálculos. Una importación, guardado de formulario, envío de pedido, cambio de contraseña o generación de credenciales sigue requiriendo su acción explícita. Los relojes locales de tiempo transcurrido y los controles de seguridad de sesión mantienen su frecuencia independiente.

Validación local: pruebas del API sobre valor inicial, persistencia, permisos y límites. Pruebas de React sobre las cuatro vistas de Operaciones, filtros aplicados, intervalo configurable, panel oculto, consultas lentas, desconexión, cancelación, errores, detalles abiertos y edición pendiente. Compilación de la web. Pendiente contrastar las consultas periódicas con EXIT real tras desplegar en desarrollo.
