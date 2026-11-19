# Criterio de consumo y cálculo por delegación

Al ejecutar un cálculo desde la herramienta se guardan las tres propuestas (media, mediana y moda), usando la misma extracción para cada material/delegación. Los filtros de resultados seleccionan delegación y criterio sin recalcular ni consultar EXIT; los contadores, la ordenación, el detalle y Excel siguen esos filtros. Los cálculos anteriores solo ofrecen su criterio original y requieren un cálculo nuevo para guardar los tres.

La media es la vista inicial. En los nuevos cálculos (`NET_PERIOD_V2`) es (todas las ventas − todas las devoluciones del periodo) ÷ días reales analizados. Los negativos diarios se conservan: una devolución en un día sin ventas reduce igualmente el neto del periodo. Se cuentan todos los días, incluso los sin movimientos, con el periodo efectivo limitado por el filtro, history_days y fecha de alta. No se extrapolan meses incompletos ni se promedian medias mensuales. La referencia mensual conservada para filtros/compatibilidad es media diaria × 30; no interviene en la obtención de la media diaria. Mediana y moda son alternativas, tanto en reposición como en redistribución; no sustituyen la media de forma automática.

La mediana y la moda utilizan los consumos diarios netos positivos, excluyendo los días con neto cero o negativo. En caso de varias modas se utiliza la mayor y se muestra una advertencia. Si ningún valor positivo se repite, el material queda para revisión sin propuesta automática. Un histórico sin consumo positivo tiene referencia cero.

El criterio mostrado determina el consumo diario usado en mínimo, punto de reposición, máximo, cantidad propuesta y reserva de Almeiras. La desviación y la seguridad conservan el histórico diario completo. Las reglas especiales anteriores para demanda irregular y comparables se mantienen al elegir Media; las alternativas aplican directamente la referencia seleccionada. Por excluir días sin consumo, mediana y moda pueden producir cantidades mayores que la media.

La pantalla de información muestra las tres estadísticas. El criterio y la base diaria utilizados se guardan con cada cálculo y aparecen en la exportación a Excel. Los cálculos antiguos sin criterio explícito se interpretan como Media. El sobrestock se presenta sin decimales; la precisión interna de los traslados y sus múltiplos se conserva.

Al calcular varias delegaciones desde la herramienta, se completan todos los lotes de una delegación antes de comenzar la siguiente. El progreso indica la delegación y cuenta combinaciones material/delegación. Solo cuando termina el trabajo completo se publican los cálculos guardados y se comprueba conjuntamente la disponibilidad de Almeiras para evitar asignar dos veces su stock. Los cálculos publicados anteriores permanecen disponibles si el nuevo trabajo falla.

Redistribución permite elegir un criterio independiente. Con los cálculos nuevos lee directamente la propuesta ya guardada de ese criterio. Para los cálculos anteriores recalcula necesidades y máximos usando el histórico inmutable de cada cálculo guardado, sin consultar de nuevo EXIT ni modificar dichos cálculos. Se requieren todas las delegaciones; un histórico antiguo que no permita recalcular exige generar un cálculo nuevo. Cambiar el criterio invalida la propuesta anterior y requiere volver a calcular antes de exportar. El Excel identifica el criterio elegido y comprueba que la propuesta y sus fuentes siguen vigentes.


## Posibles consumos spot (informativo)

La referencia habitual es la mediana de los días con consumo neto positivo, por material y delegación. Con al menos 8 días positivos se señalan días que superen estrictamente max(3 × mediana, Q3 + 1,5 × (Q3 − Q1)). Los cuartiles usan interpolación lineal en la posición (n − 1) × p. La valla superior procede del método de Tukey descrito por [NIST](https://www.itl.nist.gov/div898/handbook/eda/section3/boxplot.htm); el mínimo de 8 días y el margen 3 × mediana son decisiones conservadoras de esta herramienta, no umbrales universales de compras spot. Se informa de histórico insuficiente o de ausencia de consumo sin dar una falsa clasificación de normalidad.

La tabla identifica los materiales a revisar; el detalle incluye fechas, cantidades, proporción de los netos diarios positivos e impacto sobre la media. La media orientativa sin picos elimina las cantidades netas de los días señalados y conserva todos los días y todas las devoluciones; divide entre los días reales en NET_PERIOD_V2. En cálculos anteriores conserva la normalización mensual original. No altera cantidades, seguridad, criterios guardados ni redistribución. Triángulos rojos identifican esos días en el gráfico semanal; las barras marrones siguen identificando únicamente máximos semanales, que no son necesariamente atípicos.

El histórico disponible está agregado por día: no identifica un pedido individual ni prueba que la operación fuera spot. Una concentración de pedidos, una obra, una promoción o la estacionalidad pueden producir picos válidos. La decisión de excluir una demanda o cambiar la reposición exige revisar su contexto; no se excluye automáticamente.


La lista muestra el neto del periodo y una bandera de análisis. El balance de vendido, devuelto, neto y días reales se muestra en el detalle de los nuevos cálculos. El aviso de posible spot se destaca en ámbar e indica la proporción de consumo afectada. La falta de análisis de un cálculo anterior se identifica expresamente como «Excepcionalidad sin analizar», diferenciada de «Sin picos atípicos detectados». No se recalcula automáticamente al mostrar la marca.


## Indicador de excepcionalidad por material/delegación

El indicador identifica rareza con uno, dos o más días de consumo. Usa frecuencia (días positivos / días observados), concentración (porcentaje del consumo neto en los 3 mayores días) y picos atípicos. Con periodos de al menos 30 días, marca alta excepcionalidad si la concentración alcanza el 80 % o los días con picos acumulan al menos el 25 % del consumo neto total; marca consumo poco frecuente si hay consumo en el 10 % de días o menos o menos de 8 días positivos. Con menos de 30 días observados se señala interpretación limitada. Sin consumo se indica expresamente; ausencia de señales no garantiza recurrencia.

Estos umbrales son reglas orientativas de gestión, no una probabilidad estadística ni confirmación de una compra spot. La concentración permite identificar un material consumido solo una o dos veces aunque no haya muestra suficiente para el método de cuartiles. Un día puede agrupar varios pedidos. El indicador conserva la media, la seguridad y las cantidades calculadas: no excluye ni bloquea automáticamente por el mero número de días.

La columna «Excepcionalidad» aparece junto al consumo promedio. Excel simplificado y ampliado incluyen estado y motivos, días de consumo, frecuencia, concentración en los tres mayores días, mayor cantidad diaria y fecha. El detalle muestra las fechas y cantidades de esos días. Los cálculos anteriores necesitan una ejecución nueva para almacenar el indicador completo; abrir el detalle puede obtenerlo de la instantánea histórica sin leer EXIT.

## Carga de resultados sin actualización periódica

Reposición carga el último cálculo una vez al entrar. Solo consulta periódicamente el progreso de un trabajo en cola o en ejecución. Al terminar o fallar, esa consulta se detiene: los resultados cargados no se sustituyen al volver a la ventana, recuperar la conexión o pasar el tiempo. Cambiar filtros, paginar, abrir un cálculo guardado o ejecutar uno nuevo son acciones explícitas que cargan los datos necesarios. La lista de cálculos guardados conserva su botón de actualización manual.


### Consumo propio de Almeiras

El selector de delegación permite calcular Almeiras (00) o las cinco delegaciones, completando una antes de pasar a la siguiente. Se mantienen las tres bases (media, mediana y moda), stock físico, pendientes, histórico y exportación Excel. El cálculo de Almeiras se guarda y se sustituye independientemente del de cada delegación. Las cuatro delegaciones siguen siendo las necesarias para calcular redistribución; Almeiras conserva su papel de central receptora de excedentes. Su necesidad propia no se cuenta como un traslado desde sí misma ni consume dos veces el stock disponible.

### Impacto de picos y excepcionalidad

Detectar una cantidad diaria atípica no basta para elevar toda la referencia a alta excepcionalidad. Se conserva la detección con mediana y cuartiles, pero la bandera alta por picos exige que estos sumen al menos el 25 % del consumo neto del periodo. La regla de concentración del 80 % en los tres mayores días se mantiene. Los umbrales son reglas orientativas de revisión de esta herramienta; no demuestran una compra spot. Cuando hay consumo recurrente y los picos tienen poco peso, se indica «Consumo recurrente · picos de bajo impacto» y se conserva el detalle de esos días.

Se muestra la media de los días con consumo junto con la mediana calculada sobre esos mismos días. La media de referencia para reponer sigue incluyendo ceros y la normalización mensual, por lo que no se compara directamente con la mediana de días positivos. Esta revisión cambia el indicador, no elimina cantidades ni cambia el cálculo de las propuestas. El detalle utiliza el histórico guardado; para actualizar las banderas almacenadas del listado y su exportación hay que generar un cálculo nuevo.


### Redistribución por filtros y bloques

La pantalla permite filtrar antes de calcular por código o descripción de material, lista de códigos, área, familia, subfamilia y tipo de producto. La clasificación corresponde a la instantánea de los cálculos guardados. Se fija la selección al iniciar el proceso y cada material seleccionado se compara con sus cuatro delegaciones; los filtros no eliminan delegaciones de origen o destino de ese material. Los filtros se guardan con la propuesta y se incluyen en el Excel.

La petición solo encola una redistribución persistente. El trabajador existente de reposición identifica la selección en segundo plano y procesa bloques de hasta 1.000 materiales. Cada bloque confirma juntos su resultado y el avance; una interrupción retoma los bloques sin terminar, con un máximo de tres intentos por bloque. La pantalla muestra fase, porcentaje, materiales y bloques procesados, consulta el avance cada dos segundos solo mientras esté en cola o en ejecución y recupera el último proceso del operador al regresar.

La propuesta no se publica hasta completar todos los bloques. Cada bloque y la publicación comprueban los identificadores, versiones y huellas de los cálculos vigentes. Si alguien recalcula o ajusta uno de ellos durante el trabajo, se detiene con un mensaje para repetir la redistribución con datos coherentes. No se modifica el cálculo de reposición ni se consulta EXIT. Los criterios antiguos se reconstruyen únicamente desde sus bloques guardados; si una instantánea antigua supera 1.000 materiales y no guarda el criterio solicitado, se pide recalcular la delegación en vez de reconstruir todo su histórico en memoria.

Los movimientos se sirven en páginas de hasta 100 filas. Las alertas y necesidades pendientes muestran una vista de los primeros 100 registros; el Excel contiene todos los registros de la selección original. La búsqueda de movimientos pagina el resultado almacenado y no limita el Excel. Exportar recorre los resultados guardados por bloques y no vuelve a ejecutar el motor. Una propuesta cuyo origen cambió no se exporta. Se conservan las dos últimas propuestas terminadas correctamente por operador para limitar almacenamiento.

Las tablas `redistribution_jobs` y `redistribution_batches` se crean mediante el arranque habitual e idempotente de la aplicación. No requieren un trabajador adicional: se usa el contenedor existente `replenishment-worker`, con su bloqueo de exclusión. Los clientes antiguos reciben un aviso para usar la cola si intentan calcular o regenerar una exportación síncrona de más de 1.000 materiales. Los errores no JSON se muestran como un mensaje de servidor legible.

## Detalle por movimiento

Cada fila de la propuesta de redistribución ofrece **Ver cálculo**, incluidas las devoluciones a Almeiras. El visor muestra las existencias, entradas, compromisos, consumo del criterio, desviación, plazos, seguridad, mínimo, punto, máximo, objetivo elegido, necesidad y múltiplos utilizados en origen y destino; también muestra la fecha y versión de los cálculos de origen. Los ajustes manuales conservados se identifican expresamente.

El detalle sustituye los valores en la fórmula del sobrante físico, explica el redondeo y registra el sobrante/necesidad antes y después de la asignación. En devoluciones, muestra lo ya asignado y el orden anterior de propuestas. Si quedan necesidades incompatibles con el múltiplo común, incluye sus cantidades y el máximo que podría asignarse respetando ese formato. No aplica un objetivo de reposición de Almeiras a las devoluciones de sobrante.

Los cálculos nuevos guardan esa evidencia por movimiento junto con el bloque, bajo la misma huella de la propuesta. Se carga únicamente al pulsar el botón: la tabla paginada mantiene sus filas pequeñas, sin históricos ni detalles completos. No se recalcula ni se consulta EXIT al abrir un detalle nuevo.

Para una propuesta anterior sin evidencia persistida, se reconstruye únicamente el material solicitado a partir de las mismas instantáneas guardadas y se verifica que origen, destino, tipo y cantidad coincidan con el movimiento original. El visor lo identifica como reconstruido. Si no coincide, requiere volver a calcular la redistribución. Las comprobaciones de usuario, publicación completa y versión de las fuentes también se aplican al detalle.


## Alerta de reposición sin cobertura de Almeiras

Cada resultado muestra una marca independiente de la excepcionalidad del consumo. Rojo indica una cantidad base a reponer mayor que cero y ningún disponible para despacho en Almeiras; ámbar indica disponible positivo que no cubre la propuesta conjunta. Gris identifica disponibilidad sin confirmar, sin afirmar que el stock sea cero. Si falta la disponibilidad calculada pero el stock físico conocido de Almeiras es cero, se puede afirmar que no hay stock despachable. Las entradas pendientes no se suman al disponible físico.

Para la línea de Almeiras (00), la alerta de falta de stock se basa en su propio stock físico, no en el sobrante para enviar a otras delegaciones: no se considera un traslado a sí misma. No se marcan líneas con cantidad base cero ni excluidas manualmente. Se usa la alternativa sin agrupación, el mismo criterio de la tabla; cambiar entre media, mediana y moda consulta la alternativa guardada correspondiente.

La página muestra un aviso destacado, un contador de líneas a reponer sin cobertura, una marca en cada artículo y el resaltado de su propuesta. La lista de cálculos guardados incluye el número de líneas afectadas por delegación. Un selector filtra por falta de disponible, cobertura conjunta insuficiente, ambas, o datos sin confirmar. Los filtros de cobertura completa y alerta son mutuamente excluyentes en la interfaz. El Excel filtrado incorpora la alerta.

La marca no modifica las cantidades, genera pedidos ni envía notificaciones. Describe los datos guardados en la fecha del cálculo, no el stock en tiempo real. Los contadores se refieren a líneas artículo/delegación según los filtros activos. Las proyecciones antiguas se leen con una consulta de campos puntuales del resultado guardado: no se reconstruyen históricos ni se consulta EXIT para mostrar la alerta.

### Lectura visual del consumo

El detalle del material resume la frecuencia, la cantidad habitual (mediana de días positivos), los días con picos y su peso en el consumo. Dos barras comparan la media diaria guardada con la media orientativa sin las cantidades señaladas, manteniendo los mismos días. Los porcentajes se muestran con un decimal. Los porcentajes de concentración/picos tienen como base los netos diarios positivos, para no producir proporciones superiores al 100 % cuando hay devoluciones; no sustituyen el balance firmado del periodo.

El encabezado explica el motivo concreto: concentración, picos con impacto, baja frecuencia o datos limitados. No confirma compras spot ni excluye ventas. Las fechas, los umbrales y las reglas completas quedan en desplegables cerrados de entrada; la lista conserva solo las banderas. No cambia el cálculo ni consulta EXIT.

## Trazabilidad del consumo neto (NET_PERIOD_V2)

La fuente de cada cálculo nuevo guarda la versión del método. Las instantáneas anteriores sin versión usan MONTHLY_NORMALIZED_V1: mantienen sus cifras originales al consultar, ajustar y reconstruir criterios desde su histórico. Los trabajos iniciados antes del despliegue mantienen su método en todos sus bloques; los nuevos capturan NET_PERIOD_V2. Para aplicar la corrección a una propuesta publicada hay que calcular de nuevo y, después, regenerar su redistribución. No se reescriben resultados guardados.

El Excel incluye vendido, devuelto, neto contable, días y método; el neto contable resta las cantidades originales también en cálculos anteriores, cuya propuesta sigue usando su fórmula guardada. El detalle mensual muestra ventas, devoluciones, neto firmado y media por días realmente incluidos. Si el neto total es negativo se conserva y se avisa; la base de planificación de Media se limita a cero para evitar objetivos negativos, sin inventar ventas. La desviación usa la serie diaria firmada completa. Mediana y moda continúan sobre días positivos.

Aprovisionamiento suma ventas y devoluciones de las cinco delegaciones antes de obtener la media de la red; no pierde devoluciones por recortar cada delegación/día a cero. La reserva de Almeiras y la redistribución consumen los criterios de las instantáneas correspondientes. No se crean pedidos ni se escribe en EXIT.
