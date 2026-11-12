# Criterio de consumo y cálculo por delegación

La media es la opción inicial y conserva el cálculo anterior: promedio mensual normalizado dividido entre 30. Mediana y moda son alternativas, tanto en reposición como en redistribución; no sustituyen la media de forma automática.

La mediana y la moda utilizan los consumos diarios netos positivos, excluyendo los días con consumo cero. En caso de varias modas se utiliza la mayor y se muestra una advertencia. Si ningún valor positivo se repite, el material queda para revisión sin propuesta automática. Un histórico sin consumo positivo tiene referencia cero.

El criterio elegido determina el consumo diario usado en mínimo, punto de reposición, máximo, cantidad propuesta y reserva de Almeiras. La desviación y la seguridad conservan el histórico diario completo. Las reglas especiales anteriores para demanda irregular y comparables se mantienen al elegir Media; las alternativas aplican directamente la referencia seleccionada. Por excluir días sin consumo, mediana y moda pueden producir cantidades mayores que la media.

La pantalla de información muestra las tres estadísticas. El criterio y la base diaria utilizados se guardan con cada cálculo y aparecen en la exportación a Excel. Los cálculos antiguos sin criterio explícito se interpretan como Media. El sobrestock se presenta sin decimales; la precisión interna de los traslados y sus múltiplos se conserva.

Al calcular varias delegaciones desde la herramienta, se completan todos los lotes de una delegación antes de comenzar la siguiente. El progreso indica la delegación y cuenta combinaciones material/delegación. Solo cuando termina el trabajo completo se publican los cálculos guardados y se comprueba conjuntamente la disponibilidad de Almeiras para evitar asignar dos veces su stock. Los cálculos publicados anteriores permanecen disponibles si el nuevo trabajo falla.

Redistribución permite elegir un criterio independiente. Recalcula necesidades y máximos usando el histórico inmutable de cada cálculo guardado, sin consultar de nuevo EXIT ni modificar dichos cálculos. Se requieren todas las delegaciones; un histórico antiguo que no permita recalcular exige generar un cálculo nuevo. Cambiar el criterio invalida la propuesta anterior y requiere volver a calcular antes de exportar. El Excel identifica el criterio elegido y comprueba que la propuesta y sus fuentes siguen vigentes.
