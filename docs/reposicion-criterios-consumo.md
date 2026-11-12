# Criterio de consumo y cálculo por delegación

Al ejecutar un cálculo desde la herramienta se guardan las tres propuestas (media, mediana y moda), usando la misma extracción para cada material/delegación. Los filtros de resultados seleccionan delegación y criterio sin recalcular ni consultar EXIT; los contadores, la ordenación, el detalle y Excel siguen esos filtros. Los cálculos anteriores solo ofrecen su criterio original y requieren un cálculo nuevo para guardar los tres.

La media es la vista inicial y conserva el cálculo anterior: promedio mensual normalizado dividido entre 30. Mediana y moda son alternativas, tanto en reposición como en redistribución; no sustituyen la media de forma automática.

La mediana y la moda utilizan los consumos diarios netos positivos, excluyendo los días con consumo cero. En caso de varias modas se utiliza la mayor y se muestra una advertencia. Si ningún valor positivo se repite, el material queda para revisión sin propuesta automática. Un histórico sin consumo positivo tiene referencia cero.

El criterio mostrado determina el consumo diario usado en mínimo, punto de reposición, máximo, cantidad propuesta y reserva de Almeiras. La desviación y la seguridad conservan el histórico diario completo. Las reglas especiales anteriores para demanda irregular y comparables se mantienen al elegir Media; las alternativas aplican directamente la referencia seleccionada. Por excluir días sin consumo, mediana y moda pueden producir cantidades mayores que la media.

La pantalla de información muestra las tres estadísticas. El criterio y la base diaria utilizados se guardan con cada cálculo y aparecen en la exportación a Excel. Los cálculos antiguos sin criterio explícito se interpretan como Media. El sobrestock se presenta sin decimales; la precisión interna de los traslados y sus múltiplos se conserva.

Al calcular varias delegaciones desde la herramienta, se completan todos los lotes de una delegación antes de comenzar la siguiente. El progreso indica la delegación y cuenta combinaciones material/delegación. Solo cuando termina el trabajo completo se publican los cálculos guardados y se comprueba conjuntamente la disponibilidad de Almeiras para evitar asignar dos veces su stock. Los cálculos publicados anteriores permanecen disponibles si el nuevo trabajo falla.

Redistribución permite elegir un criterio independiente. Con los cálculos nuevos lee directamente la propuesta ya guardada de ese criterio. Para los cálculos anteriores recalcula necesidades y máximos usando el histórico inmutable de cada cálculo guardado, sin consultar de nuevo EXIT ni modificar dichos cálculos. Se requieren todas las delegaciones; un histórico antiguo que no permita recalcular exige generar un cálculo nuevo. Cambiar el criterio invalida la propuesta anterior y requiere volver a calcular antes de exportar. El Excel identifica el criterio elegido y comprueba que la propuesta y sus fuentes siguen vigentes.


## Posibles consumos spot (informativo)

La referencia habitual es la mediana de los días con consumo neto positivo, por material y delegación. Con al menos 8 días positivos se señalan días que superen estrictamente max(3 × mediana, Q3 + 1,5 × (Q3 − Q1)). Los cuartiles usan interpolación lineal en la posición (n − 1) × p. La valla superior procede del método de Tukey descrito por [NIST](https://www.itl.nist.gov/div898/handbook/eda/section3/boxplot.htm); el mínimo de 8 días y el margen 3 × mediana son decisiones conservadoras de esta herramienta, no umbrales universales de compras spot. Se informa de histórico insuficiente o de ausencia de consumo sin dar una falsa clasificación de normalidad.

La tabla identifica los materiales a revisar; el detalle incluye fechas, cantidades, proporción del consumo neto e impacto sobre la media. La media orientativa sin picos elimina las cantidades netas de los días señalados y conserva todos los días, los meses y la normalización mensual original. No altera cantidades, seguridad, criterios guardados ni redistribución. Triángulos rojos identifican esos días en el gráfico semanal; las barras marrones siguen identificando únicamente máximos semanales, que no son necesariamente atípicos.

El histórico disponible está agregado por día: no identifica un pedido individual ni prueba que la operación fuera spot. Una concentración de pedidos, una obra, una promoción o la estacionalidad pueden producir picos válidos. La decisión de excluir una demanda o cambiar la reposición exige revisar su contexto; no se excluye automáticamente.


El estado del análisis spot se muestra siempre junto al consumo medio mensual del listado y dentro de la tarjeta de media diaria del detalle. El aviso de posible spot se destaca en ámbar e indica la proporción de consumo afectada. La falta de análisis de un cálculo anterior se identifica expresamente como «Excepcionalidad sin analizar», diferenciada de «Sin picos atípicos detectados». No se recalcula automáticamente al mostrar la marca.


## Indicador de excepcionalidad por material/delegación

El indicador identifica rareza con uno, dos o más días de consumo. Usa frecuencia (días positivos / días observados), concentración (porcentaje del consumo neto en los 3 mayores días) y picos atípicos. Con periodos de al menos 30 días, marca alta excepcionalidad si la concentración alcanza el 80 % o hay picos; marca consumo poco frecuente si hay consumo en el 10 % de días o menos o menos de 8 días positivos. Con menos de 30 días observados se señala interpretación limitada. Sin consumo se indica expresamente; ausencia de señales no garantiza recurrencia.

Estos umbrales son reglas orientativas de gestión, no una probabilidad estadística ni confirmación de una compra spot. La concentración permite identificar un material consumido solo una o dos veces aunque no haya muestra suficiente para el método de cuartiles. Un día puede agrupar varios pedidos. El indicador conserva la media, la seguridad y las cantidades calculadas: no excluye ni bloquea automáticamente por el mero número de días.

La columna «Excepcionalidad» aparece junto al consumo promedio. Excel simplificado y ampliado incluyen estado y motivos, días de consumo, frecuencia, concentración en los tres mayores días, mayor cantidad diaria y fecha. El detalle muestra las fechas y cantidades de esos días. Los cálculos anteriores necesitan una ejecución nueva para almacenar el indicador completo; abrir el detalle puede obtenerlo de la instantánea histórica sin leer EXIT.
