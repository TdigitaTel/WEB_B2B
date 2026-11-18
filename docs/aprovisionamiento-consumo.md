# Propuesta de compra por consumo

La pestaña **Aprovisionamiento** prepara una propuesta independiente de la reposición interna. No genera pedidos ni escribe en EXIT. Comparte el permiso de Reposición y cada operador recupera sus propios cálculos.

## Datos y alcance

- Red completa: Almeiras (00), San Diego (01), Ferrol (02), Santiago (04) y Sanxenxo (05).
- Ventas de cliente de empresa 1: albaranes, mismas unidades y periodo que Reposición. Las devoluciones se descuentan en cada artículo/delegación/día, con suelo cero, y después se agrega la demanda diaria de la red. No se suman las propuestas de reposición interna como demanda.
- Stock: una fila por artículo/delegación de VIS_EX_StockVentasDelegacion. Se suman UnidadSaldo, PendienteRecibir y PendienteServir una sola vez. Si falta alguna delegación no se supone stock cero: la compra queda para revisión.
- Artículos de empresa 1. Aprovisionamiento representa días de cobertura; DiasReposicion representa plazo previsto de entrega en días, según confirmación del usuario. Para 03283: 90 y 5, respectivamente.
- Marca: articulos LEFT JOIN Marcas por CodigoMarca **y CodigoEmpresa**. Una marca sin coincidencia no elimina el artículo; duplicados provocan un error explícito.
- Clasificaciones del catálogo B2B y su visibilidad vigente al calcular; la instantánea conserva nombres e identificadores.

## Fórmula

Para cada material y criterio guardado (media, mediana, moda):

    H = Aprovisionamiento + DiasReposicion
    seguridad = Z × desviación diaria de la red × sqrt(H), o 0 si se desactiva
    objetivo = consumo diario de referencia × H + seguridad
    disponible previsto = stock red + entradas pendientes − salidas comprometidas
    compra base = ceil(max(0, objetivo − disponible previsto))
    alternativa con múltiplo EXIT = ceil(compra sin redondear / EX_multiplo) × EX_multiplo

La media mantiene el promedio mensual normalizado ÷ 30, incluidos los días sin consumo. Mediana y moda usan días con consumo positivo; pueden dar cantidades mayores. En empate de moda se usa la mayor; si no hay valores repetidos, se marca revisión con este criterio.

La seguridad es una aproximación de revisión periódica: protege cobertura y entrega; asume demanda diaria independiente y plazo estable. El porcentaje elegido no garantiza un servicio observado. No hay histórico de plazos reales del proveedor ni fechas de llegada de las entradas en esta fuente. Se deben comprobar esos plazos, especialmente con demanda intermitente o estacional.

Ejemplo ilustrativo, **no son los consumos reales de 03283**: consumo 10 UD/día, cobertura 90, entrega 5, seguridad desactivada, stock red 100, entradas 10 y salidas 5. Objetivo 950; disponible 105; compra base 845; con múltiplo 12, 852.

## Revisión y limitaciones

- Cobertura/plazo ausentes, no finitos o fuera de rango, stock incompleto o moda no disponible: compra `null` / **Revisar**, nunca un cero que aparente ausencia de necesidad.
- No hay compra por consumo cero; no se inventan ventas ni mínimos de exposición.
- La excepcionalidad es un flag informativo: no se descuentan ventas puntuales automáticamente. Un único día de consumo muestra aviso.
- Entradas y salidas de un traslado interno compensado se cancelan en el disponible de la red. Si solo consta un lado o los traslados en tránsito se representan de otra manera, el operador debe revisarlos antes de comprar. Las entradas sin fecha pueden llegar después de una rotura prevista.
- EX_multiplo es el múltiplo de **despacho** conocido. Se ofrece como alternativa; confirmar el formato de compra del proveedor, su mínimo y sus condiciones antes de emitir un pedido.
- Stock negativo, poco histórico y entradas pendientes generan avisos. Estos indicadores no reemplazan una revisión comercial.

## Proceso y consulta

Se ejecuta en el proceso de reposición existente, con su bloqueo global, fuera de la API, después de los trabajos de reposición pendientes. Se congela una lista de artículos y se procesan bloques de hasta 1.000; origen, resultados y progreso se guardan atómicamente. Una interrupción reanuda los bloques pendientes. El resultado se publica únicamente al completar todo; un fallo conserva la propuesta anterior.

La pestaña ofrece filtros de cálculo por área, familia, subfamilia, tipo, códigos y marca (código o nombre EXIT). Los resultados permiten filtrar por clasificación, marca, búsqueda y solo a comprar; se paginan en servidor. Cambiar el criterio o los filtros de consulta no recalcula ni consulta EXIT. El Excel incluye todos los resultados filtrados, las fórmulas, los parámetros, los valores de origen y los avisos. Se conservan dos propuestas exitosas por operador.

Las tablas procurement_jobs, procurement_batches y procurement_results se crean mediante el bootstrap habitual. No hay modificación manual pendiente de tablas existentes. El proceso de reposición y la API deben desplegarse juntos para habilitar el cálculo.
