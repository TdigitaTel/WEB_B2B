# Histórico en la información de cada material

En Reposición, abrir el código del material o «Ver datos» muestra:

- Mediana del consumo diario: valor central de los días con consumo positivo ordenados (promedio de los dos centrales si hay un número par de días).
- Moda del consumo diario: todos los valores positivos con la máxima frecuencia entre los días con consumo. Si ningún valor se repite, se muestra «Sin moda».
- Gráfico de ventas brutas por semanas de lunes a domingo, con los máximos destacados y una tabla desplegable con cantidades exactas, devoluciones y consumo acumulado.

Las estadísticas corresponden al artículo y delegación de esa línea y a la instantánea guardada del cálculo. Usan consumo diario = máximo entre cero y ventas menos devoluciones. La mediana y la moda excluyen los días cuyo consumo neto es cero e indican cuántos días positivos se han incluido. Si no hay días positivos, muestran «Sin consumo positivo». El gráfico semanal conserva todos los días del periodo, también los de ventas cero. La desviación y las fórmulas de reposición mantienen su criterio actual, con los días cero incluidos. El rango efectivo respeta tanto las fechas seleccionadas como el límite de histórico o el alta del artículo cuando sean aplicables. Las semanas de los extremos solo incluyen los días dentro del rango; no se extrapolan.

Estos indicadores son informativos: no sustituyen el promedio ni modifican el stock de seguridad o la cantidad propuesta. La unidad se conserva tal como llega de EXIT.

La evidencia se obtiene al abrir la línea desde el endpoint de detalle existente, también para cálculos anteriores que conserven su instantánea. No se vuelve a consultar EXIT ni se incluyen series semanales en todas las filas de las páginas de resultados. No requiere migraciones.


## Frecuencia y ubicación temporal de mediana y moda

El detalle indica cuántos días tuvieron exactamente el valor de la mediana y cada moda, junto con su porcentaje sobre los días de consumo positivo. También muestra la proporción de días con actividad respecto al periodo completo. «Mayoría» significa estrictamente más del 50 % de los días positivos; no se asignan niveles de confianza ni se afirma estacionalidad por frecuencia solamente.

Si la mediana es un valor intermedio que nunca se observó (por ejemplo, mediana 2 para consumos 1, 1, 3, 3), su frecuencia es cero. La pantalla explica el motivo y no inventa fechas.

El gráfico mantiene las barras de ventas brutas semanales y añade dos líneas inferiores con ocurrencias **diarias**: círculos verdes para la mediana y rombos violetas para las modas. Cuando ambos indicadores coinciden en una fecha se ven en las dos líneas. Las marcas comparten un eje de fechas continuo con las barras, pero no representan totales semanales. Sus títulos y una tabla desplegable permiten consultar fechas, cantidades y coincidencias exactas.

Fondos alternos y rótulos en marca de agua separan los meses naturales. Los límites se sitúan en el primer día de cada mes, aunque la semana cruce entre meses o el periodo empiece o termine a mitad de mes. Las estadísticas se reconstruyen de la instantánea guardada, también para los cálculos anteriores.
