# Cálculos vigentes por delegación y redistribución

Reposición conserva un cálculo vigente por cada una de las delegaciones operativas: 01, 02, 04 y 05. La lista es compartida entre operadores e indica la fecha del cálculo, el periodo de ventas y el número de materiales. «Ver cálculo» carga únicamente la delegación elegida; los filtros, contadores y Excel corresponden a esa delegación.

## Sustitución

Los cálculos se publican después de completar todos los bloques. Al recalcular una o varias delegaciones, se sustituyen solo sus cálculos anteriores; los de las demás permanecen disponibles. Un trabajo fallido o incompleto no sustituye el resultado vigente.

Se eliminan los resultados y ajustes anteriores de la delegación sustituida. Si la instantánea todavía sirve a otras delegaciones se conserva su fuente compartida; cuando ya no sirve a ninguna se eliminan la instantánea y los bloques de origen. El registro ligero del trabajo queda como `REPLACED`. No se elimina información de EXIT.

La tabla nueva `replenishment_delegation_calculations` tiene una fila por delegación y referencia su cálculo vigente. Se crea con el arranque habitual del backend (`bootstrap`). En instalaciones anteriores, la lista adopta el último cálculo publicado disponible para cada delegación; no adopta trabajos pendientes/fallidos ni vistas previas sin resultados.

## Propuesta de redistribución

«Calcular redistribución» usa los cuatro cálculos vigentes guardados, sin consultar ni modificar EXIT. Si falta alguna delegación, responde con una alerta que identifica cuáles faltan y no calcula movimientos.

Para cada material:

1. Debe existir una línea en las cuatro delegaciones, con unidades coincidentes y stock, pendientes y objetivos válidos. Los materiales incompletos se excluyen y se muestran para revisión; nunca se interpreta una línea ausente como necesidad cero.
2. El excedente transferible de cada origen es `máximo(0, stock físico − pendiente de servir − stock máximo calculado)`, redondeado hacia abajo al formato de despacho. Las entradas pendientes no se pueden trasladar todavía.
3. La necesidad de cada destino es su cantidad final a reponer. Se atienden primero los destinos sin disponible previsto y después los de menor cobertura; los empates se resuelven por código de delegación. Los orígenes se ordenan por mayor excedente. Esta prioridad es determinista y no representa optimización por distancia o coste.
4. Se propone como máximo el mínimo entre excedente restante y necesidad restante, respetando los múltiplos de ambos extremos. No se asigna el mismo excedente dos veces ni se sobrepasa la necesidad guardada para completar un múltiplo.
5. El excedente despachable que no se pueda asignar a otro destino se propone devolver a Almeiras (00). Las necesidades sin cubrir se muestran aparte; no se promete que Almeiras las cubra usando estas devoluciones futuras.

La tabla muestra material, origen, destino, cantidad/unidad y motivo. Incluye las fechas de consulta de stock y periodos de ventas utilizados y una advertencia si los periodos difieren. La propuesta es informativa: no crea pedidos, movimientos ni reservas reales. No suma cantidades de unidades distintas en un total global.


## Pestañas y Excel

La pestaña «Cálculo de reposición» contiene los parámetros, el progreso y la tabla de resultados. «Redistribución» agrupa los cálculos vigentes por delegación y la propuesta de movimientos. Cambiar de pestaña conserva los parámetros y la propuesta; «Ver cálculo» abre la delegación elegida en la primera pestaña.

Después de calcular la redistribución, «Exportar redistribución a Excel» descarga la propuesta completa (la búsqueda visible no recorta el archivo). El libro incluye Movimientos, Necesidades sin cubrir, Alertas, Cálculos utilizados y Resumen. Conserva códigos con ceros iniciales y cantidades numéricas; los textos del catálogo se escriben como texto de Excel, sin ejecutar fórmulas.

El servidor comprueba la referencia de la propuesta antes de exportar. Si otro cálculo o ajuste cambia su contenido, responde solicitando recalcular; no descarga una propuesta diferente de la revisada. La exportación usa los cálculos guardados y no escribe movimientos en EXIT.
