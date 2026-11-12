# Lectura de cálculos de reposición guardados

La pantalla restaura metadatos de la simulación sin descargar su instantánea completa de artículos, ventas y stocks. El último trabajo finalizado comparte esos metadatos con el resultado inicial; no los vuelve a cargar dos veces.

Los filtros, la ordenación y los contadores utilizan `replenishment_results.filter_data`, una proyección pequeña de los valores ya calculados para media, mediana y moda. No contiene históricos, parámetros de planificación ni explicaciones extensas. El listado sigue paginado en la base de datos; únicamente las filas de la página solicitada cargan su documento completo. Un índice `(scenario_id, delegation, sku)` permite localizar y ordenar materiales dentro de una delegación. No hay consultas adicionales por cada material del listado.

Los cambios manuales actualizan documento y proyección en la misma transacción mediante eventos de persistencia. La inserción masiva del trabajador genera explícitamente ambas representaciones; la publicación de cobertura conjunta mantiene también la proyección. Filtros y Excel comparten las mismas condiciones y contadores.

El detalle conserva las cantidades y objetivos guardados. Para pintar el gráfico agrega únicamente las ventas históricas del material y delegación seleccionados, sin ejecutar el cálculo de reposición, preparar comparables ni calcular otras delegaciones. No consulta EXIT. Las acciones explícitas de ajuste y recálculo siguen disponibles y mantienen sus verificaciones.

## Actualización de instalaciones existentes

El arranque incorpora automáticamente la columna y el índice. Adapta los resultados anteriores en lotes de 100 filas y confirma cada lote, sin recalcularlos ni alterar su documento original. Un reinicio retoma solo las filas pendientes. En PostgreSQL bloquea cada lote seleccionado para impedir que sobrescriba una proyección actualizada por un ajuste concurrente. Esta adaptación inicial puede alargar el primer arranque; los siguientes no la repiten. Se requiere la misma cuenta de migración que utiliza habitualmente el despliegue. No hace falta generar nuevamente los cálculos.

## Validación de rendimiento

Prueba sintética local: 8.000 combinaciones material/delegación, tres criterios y 36 registros mensuales por criterio. Mediana de cuatro consultas equivalentes de contadores, con el criterio mediana y una delegación: 1.003,30 ms leyendo documentos completos y 116,12 ms usando la proyección (8,64 veces). Documento de muestra: 15.866 bytes; proyección: 944 bytes. Se verificó igualdad de contadores. Esta medición usa SQLite local y no constituye una medición de la instalación PostgreSQL ni del tiempo total de carga en el navegador. Tras desplegar en desarrollo se debe comparar la duración de `/jobs/current`, `/results` y el detalle con los datos reales.
