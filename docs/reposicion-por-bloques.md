# Reposición por bloques

La pantalla encola el cálculo (`POST /api/v1/store/replenishment/jobs`, HTTP 202). No consulta EXIT ni realiza cálculos dentro de esa petición. `GET /jobs/{id}` devuelve estado, fase, artículos y bloques guardados; `GET /jobs/current` recupera el último trabajo y el último resultado completo del usuario al volver a la pantalla.

## Persistencia y publicación

- `replenishment_jobs`: selección, parámetros, límite de artículos al comenzar, estado y progreso.
- `replenishment_batches`: lista congelada de códigos de cada bloque (máximo 1.000), datos de EXIT y huella de origen.
- `replenishment_scenarios`: cabecera del cálculo, con metadatos pequeños para los cálculos por bloques.
- `replenishment_results`: resultados por artículo/delegación. Cada artículo se procesa junto con todas las delegaciones seleccionadas, para comprobar correctamente la necesidad conjunta frente a Almeiras.

Se identifica primero la lista de artículos activos, respetando la clasificación y códigos seleccionados y el límite configurado. Solo se carga el histórico de ventas y stock de un bloque cada vez. Se calcula la fórmula simple visible de la web, sin comparables entre artículos ni reglas ocultas. Datos de origen, resultados y contadores del bloque se confirman en la misma transacción. El progreso cuenta artículos confirmados, no delegaciones ni filas leídas.

Las consultas de resultados, detalle, ajustes y Excel rechazan cálculos incompletos (409), aunque ya haya bloques guardados. Al terminar todos los bloques, se publica mediante un único cambio de estado a COMPLETED; solo entonces el progreso llega al 100 %. El resultado completo anterior continúa disponible durante la ejecución o si esta falla. Una selección vacía termina con una tabla vacía. No se trunca silenciosamente una selección que supere el límite.

El stock se consulta a lo largo de la ejecución, **no en un único instante**. La cabecera muestra inicio y fin de la extracción. El detalle histórico usa exclusivamente el bloque guardado, sin volver a leer EXIT. El Excel usa los mismos filtros y resultados persistidos que la tabla.

## Proceso de servidor

El servicio Docker Compose `replenishment-worker` utiliza la misma imagen de la API y ejecuta `python -m app.replenishment_worker`. Se inicia con el despliegue habitual de desarrollo o producción; no requiere configurar cron ni un servicio Linux manual. Las tablas nuevas se crean mediante el bootstrap habitual de la API, antes de iniciar el proceso.

El trabajador tiene por defecto un límite de 1 CPU y 1.536 MB, ajustables en el archivo privado del entorno con `REPLENISHMENT_WORKER_CPUS` y `REPLENISHMENT_WORKER_MEMORY`. Son límites del trabajador, no de la API. El tamaño de bloque es de 1.000 artículos; no modifica el límite total configurado en la web. No se garantiza que cualquier histórico quepa en esa memoria: si el contenedor muere repetidamente en un bloque debe revisarse la memoria y el volumen de datos.

En PostgreSQL un bloqueo asesor de sesión serializa los trabajadores, también durante un despliegue. Las peticiones de la web no adquieren ese bloqueo. Cada usuario puede tener un trabajo en cola/en curso; los de otros usuarios esperan turno. Un token por ejecución evita que un proceso antiguo confirme avances después de ceder el trabajo. Al reiniciar se retoma el trabajo RUNNING más antiguo y solo sus bloques sin confirmar. Tras tres interrupciones del mismo bloque se marca FAILED para evitar un ciclo de reinicios permanente. Un error de consulta o cálculo se registra y marca FAILED sin publicar datos parciales; el usuario puede iniciar un cálculo nuevo.

Diagnóstico: `docker compose ... ps replenishment-worker` y `docker compose ... logs --tail=100 replenishment-worker`. Una ejecución QUEUED espera al trabajador; si no avanza, comprobar que este servicio está levantado con la versión nueva. Esta entrega no programa ejecuciones diarias ni genera pedidos ni modifica EXIT.

El endpoint síncrono antiguo `/simulations` se conserva para compatibilidad y pruebas con un máximo de 1.000 artículos; la pantalla utiliza siempre la cola, incluso para selecciones pequeñas.

## Validación

Pruebas con fuentes simuladas: 2.005 artículos y cuatro delegaciones en bloques 1.000 + 1.000 + 5; guardados intermedios inaccesibles desde resultados/Excel; recuperación tras interrupción sin duplicados; conservación del resultado anterior ante fallos; corte tras interrupciones repetidas; límite congelado; acceso al progreso restringido al propietario; equivalencia de cantidades y cobertura conjunta con el motor original; Excel y detalle desde el origen guardado. Pendiente validar tiempos y memoria con SQL Server y PostgreSQL reales en desarrollo.
