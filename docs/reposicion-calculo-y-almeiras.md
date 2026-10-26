# Cálculo de reposición y protección de Almeiras

La pantalla contiene un cálculo, sus parámetros, resultados filtrables y Excel. Se retiran de la interfaz los escenarios, políticas, comparativos y edición de escenarios. Las rutas de listar/guardar escenarios y comparar ya no están disponibles. No se borran las instantáneas históricas: sirven de trazabilidad y quedan disponibles para una fase posterior. Las tablas con nombres anteriores siguen siendo almacenamiento interno del cálculo. Los cálculos nuevos no aplican políticas guardadas ocultas: utilizan sus parámetros visibles.

## Fórmulas visibles

- `d`: consumo medio diario de la delegación. Se suman los consumos diarios `max(0, vendido − devuelto)` y se dividen entre todos los días del periodo, incluidos los días sin ventas. El consumo mensual equivalente es `d × 30`.
- `σ`: desviación poblacional de esos consumos diarios.
- `R`: días hasta la próxima reposición (inicial: 7).
- `L`: plazo de llegada en días (inicial: 1).
- `M`: días de cobertura del stock máximo (inicial: 30; no puede ser inferior a R).
- `Z`: cuantil normal del nivel de servicio seleccionado (95 % ≈ 1,645).
- Seguridad: `ceil(Z × σ × sqrt(L + R))`.
- Stock mínimo: `ceil(d × L + seguridad)`.
- Punto de reposición, conservando la definición acordada para esta aplicación: `ceil(stock mínimo + d × R)`.
- Stock máximo: `ceil(stock mínimo + d × M)`.
- Disponible previsto: `stock + pendiente de recibir − pendiente de servir`.
- Necesidad: `max(0, objetivo elegido − disponible previsto)`.
- Si se eligen múltiplos EXIT, se redondea hacia arriba a `articulos.EX_multiplo`. Sin un múltiplo positivo válido, la cantidad queda a cero con aviso.

Se puede elegir entre punto y máximo. El cálculo simple utiliza estas fórmulas también con demanda irregular (con aviso para revisión); no inventa consumo con artículos comparables. La incertidumbre del modelo sigue existiendo aunque una fórmula produzca un número: el nivel de servicio no es una garantía de disponibilidad. Las fechas de alta futuras impiden proponer reposición.

Ejemplo: mínimo 21, consumo mensual equivalente 63,274, R=7, M=30, disponible previsto 24. Punto=36 → necesidad 12. Máximo=85 → necesidad 61 antes de agrupar. Ambos objetivos son distintos porque sus plazos de cobertura son explícitos.

## Almeiras (delegación 00)

La extracción de ventas incorpora `IdDelegacion='00'` en las mismas tablas, campos, periodo y empresa ya utilizados. Se conserva la vista de stock indicada en el proyecto, sin inventar campos de empresa ni desglosar almacenes. Esta implementación requiere validar en desarrollo que la fila 00 corresponde efectivamente al stock de Almeiras apto para transferir.

Con consumo propio `d00`, desviación `σ00` y `C` días de reserva (inicial: 7):

- Seguridad propia = `ceil(Z × σ00 × sqrt(L + C))`.
- Reserva propia = `ceil(d00 × (L + C) + seguridad propia)`.
- Stock físico libre = `max(0, stock00 − pendiente de servir00)`.
- Disponible para despacho = `max(0, stock físico libre − reserva propia)`.

El pendiente de recibir de Almeiras se muestra como información y **no se ofrece para despacho físico**. Se suma la necesidad final, ya agrupada, de todas las delegaciones seleccionadas para cada artículo. Solo se indica «Cubre conjunto» cuando esa suma cabe en el disponible protegido. No se asigna el mismo stock completo a cada sede ni se hace una asignación parcial arbitraria. Si falta stock/histórico consultado, o el stock contiene valores negativos, no se confirma disponibilidad.

En detalle se muestran stock físico, comprometido, entradas pendientes, consumo mensual propio, reserva, disponible transferible, solicitud conjunta y faltante. La necesidad a reponer permanece visible aunque no se pueda despachar; no se ha creado un pedido, reserva o traslado real. Con parámetros distintos en cálculos internos heredados se toma la reserva más protectora para cada artículo.

## Sobrestock y ausencia de consumo

- Sobrestock previsto: disponible previsto mayor que el stock máximo calculado. Exceso = disponible previsto − máximo. Se marca con una etiqueta y se puede filtrar.
- Sin consumo: consumo neto diario acumulado igual a cero en el periodo de esa delegación. Se puede filtrar con/sin consumo.
- «No reponer artículos sin consumo» está activado inicialmente. Al marcarlo, su propuesta queda a cero incluso si existe una política antigua o saldo negativo. Puede desmarcarse para revisar otros casos; no genera estimaciones por comparables en la pantalla actual.
- Los filtros de disponibilidad, sobrestock y consumo se ejecutan en la consulta de resultados, antes de paginar, y no modifican el cálculo ni liberan presupuesto para otras sedes.

## Validación

Pruebas de fórmulas punto/máximo, redondeo y múltiplos, sobrestock, exclusión por falta de consumo, consumo/reserva de Almeiras, entradas pendientes no despachables, consumo desconocido, datos de stock negativos y competencia de varias delegaciones por el mismo stock. Pruebas API de filtros y exportación, y de retirada de guardar/listar/comparar escenarios. Comprobación visual local con datos ficticios. La ejecución con EXIT real y el despliegue son posteriores.
