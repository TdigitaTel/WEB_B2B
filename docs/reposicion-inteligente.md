# Reposición inteligente — MVP

Acceso independiente: Reposición, para administrador y operador.

## Fuentes y alcance

Se utilizan los nombres del documento sin sustituir tablas ni campos:

- `dbo.articulos`: `codigoarticulo`, `descripcionarticulo`, `EX_tipounidad`, `inactivo`, `fechaalta`, `codigoalternativo7` a `codigoalternativo10`. Solo `inactivo=0`.
- `dbo.AlbaranVentaCabecera` y `dbo.AlbaranVentaLineas`: unión por `NumeroAlbaran`, `EjercicioAlbaran`, `CodigoEmpresa`; empresa 1; fecha `FechaAlbaran`, delegación `IdDelegacion`, artículo `CodigoArticulo`, cantidad `Unidades`.
- `dbo.VIS_EX_StockVentasDelegacion`: `CodigoArticulo`, `IdDelegacion`, `UnidadSaldo`, `PendienteRecibir`, `PendienteServir`.
- PostgreSQL: `products.sku` enlaza con EXIT. Clasificación mediante `material_area_id`, `material_family_id`, `material_subfamily_id`, `material_product_type_id` y sus tablas maestras.

Destinos: 01 San Diego/A Coruña, 02 Ferrol, 04 Santiago y 05 Sanxenxo. El 00 es referencia central consolidada: no se duplica ni se considera automáticamente transferible. La vista indicada no incluye empresa; no se ha inventado ese filtro. Duplicados de artículo o artículo/delegación provocan un error explícito.

Todas las consultas a EXIT son SELECT. No se generan pedidos, movimientos, RPA ni tareas programadas. Límite inicial 20.000 artículos por simulación, configurable entre 1 y 100.000 en Reposición → Configuración; si se supera, hay que ampliarlo o acotar clasificación/códigos. No se trunca silenciosamente.

## Cálculo

La serie diaria incluye ceros. Ventas positivas y devoluciones negativas se conservan separadas; demanda diaria = máximo(0, ventas − devoluciones). Posición = saldo + pendiente recibir − pendiente servir.

Valores iniciales: revisión 7 días, plazo 1 día, servicio 95 %, histórico desde 01/01/2026. Precedencia de parámetros parciales: global → área → familia → subfamilia → tipo → delegación → artículo/delegación → ajuste temporal.

Demanda regular: H = revisión + plazo; seguridad = techo(z × desviación × raíz(H)); mínimo = techo(media × plazo + seguridad); punto de reposición = techo(mínimo + media × días hasta la próxima reposición); propuesta = máximo(0, objetivo aplicado − posición). El máximo estadístico queda como referencia y no determina la propuesta. Se aplican límites, mínimos y múltiplos configurados y se advierte si el redondeo supera el objetivo.

Demanda intermitente: percentil empírico de ventanas completas del horizonte, con al menos cinco ventanas y cinco días con demanda. Artículos nuevos o con evidencia insuficiente no reciben automáticamente una previsión normal. Las referencias comparables requieren al menos tres artículos de la misma unidad y clasificación, con cinco días de demanda y que no sean nuevos. Su estimación es indicativa y de confianza baja; nunca sustituye la demanda real. Sin evidencia, se propone revisión manual. Stock ausente no equivale a cero.

## Persistencia y auditoría

Tablas nuevas: `replenishment_policies`, `replenishment_scenarios`, `replenishment_results`, `replenishment_adjustments`. El arranque habitual con `Base.metadata.create_all` las crea. No se altera el esquema de EXIT.

Cada escenario conserva fuente, clasificación, parámetros, fechas de extracción y huella. Los ajustes registran usuario, motivo, valores previos y cambios; control de versión evita sobreescrituras concurrentes. Guardar una excepción permanente es una acción distinta del ajuste de escenario.

La comparación advierte si cambian fuente o ventana histórica. El stock corresponde al momento de extracción, no se reconstruye un stock histórico. Las lecturas secuenciales no garantizan una instantánea transaccional de EXIT. El Excel mantiene códigos como texto e incluye contexto de cálculo. Las sumas de cantidades de unidades distintas son orientativas.

API: `/api/v1/store/replenishment` (opciones, políticas, simulaciones, resultados, detalle, recálculo, ajustes, comparación y exportación). Filtrado, ordenación y paginación de resultados se hacen en PostgreSQL.

## Validación pendiente en el entorno real

Por indicación del usuario se confía en las tablas y campos del documento. Las pruebas locales utilizan datos de prueba: no confirman la conexión ni la extracción real de EXIT.

Antes de uso operativo: ejecutar extracción acotada; contrastar un artículo por delegación con albaranes y stock; comprobar unidades, empresa de la vista y unicidad de las tres claves de unión; revisar devoluciones, días sin venta y propuesta conjunta contra 00. Si EXIT devuelve un error de esquema, ajustar explícitamente con ese diagnóstico.

## Formato y periodo de despacho

El periodo de despacho se configura por política (clave compatible `review_days`): días de consumo a cubrir, a los que se suma el plazo de llegada (`lead_days`). Se muestra su suma en el detalle. No es el periodo histórico de ventas.

`multiple_mode` permite NONE (sin agrupación), MANUAL (parámetro `multiple`) o EXIT (campo exacto `dbo.articulos.EX_multiplo`, conservado en la captura). Se redondea hacia arriba al siguiente grupo completo y se advierte si supera el objetivo. Ejemplo: 13 unidades con múltiplo 6 → 18. El modo predeterminado MANUAL conserva las políticas anteriores.

En modo EXIT, un múltiplo ausente, cero, negativo o inválido deja la propuesta en cero con un aviso, sin asumir otro formato. Los ajustes manuales positivos deben respetar ese múltiplo o se rechazan con explicación. Excluir o ajustar a cero continúa permitido. Excel incluye múltiplo de EXIT, aplicado y cantidad previa al redondeo.

## Punto de reposición y configuración del módulo

Modelo MINIMUM_PLUS_CYCLE_DEMAND: `replenishment_point = ceil(minimum_stock + daily_mean * review_days)`; objetivo aplicado igual al punto salvo topes expresamente configurados (`max_coverage_days`, `manual_max`). Nunca se reduce por debajo del mínimo. El máximo estadístico calculado no actúa como objetivo ni límite implícito. Se descuenta stock + recibir − servir, después se aplican mínimos y múltiplos. Si el método es revisión manual por falta de evidencia, no se proyecta consumo automáticamente.

Ejemplo: consumo mensual equivalente 63,274, mínimo 21, revisión 7 días y posición 24: consumo de ciclo 14,7639, punto 36, propuesta 12 antes de agrupaciones. El plazo de llegada ya contribuye al mínimo y no se suma otra vez al ciclo.

Los escenarios anteriores mantienen sus resultados; la interfaz los identifica y la comparación avisa si difiere el modelo. El Excel incluye consumo de ciclo, punto y objetivo aplicado.

`replenishment_settings` almacena el límite del módulo (bootstrap habitual); el operador puede guardarlo desde Configuración, con auditoría. Valor inicial 20.000, máximo admitido 100.000. Se conserva el límite utilizado en la fuente de cada escenario. La extracción rechaza un exceso sin truncar resultados. La clasificación se complementa en lotes de 1.000 códigos para no exceder los parámetros de PostgreSQL.
