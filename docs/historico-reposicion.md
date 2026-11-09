# Histórico en la información de cada material

En Reposición, abrir el código del material o «Ver datos» muestra:

- Mediana del consumo diario: valor central de los días con consumo positivo ordenados (promedio de los dos centrales si hay un número par de días).
- Moda del consumo diario: todos los valores positivos con la máxima frecuencia entre los días con consumo. Si ningún valor se repite, se muestra «Sin moda».
- Gráfico de ventas brutas por semanas de lunes a domingo, con los máximos destacados y una tabla desplegable con cantidades exactas, devoluciones y consumo acumulado.

Las estadísticas corresponden al artículo y delegación de esa línea y a la instantánea guardada del cálculo. Usan consumo diario = máximo entre cero y ventas menos devoluciones. La mediana y la moda excluyen los días cuyo consumo neto es cero e indican cuántos días positivos se han incluido. Si no hay días positivos, muestran «Sin consumo positivo». El gráfico semanal conserva todos los días del periodo, también los de ventas cero. La desviación y las fórmulas de reposición mantienen su criterio actual, con los días cero incluidos. El rango efectivo respeta tanto las fechas seleccionadas como el límite de histórico o el alta del artículo cuando sean aplicables. Las semanas de los extremos solo incluyen los días dentro del rango; no se extrapolan.

Estos indicadores son informativos: no sustituyen el promedio ni modifican el stock de seguridad o la cantidad propuesta. La unidad se conserva tal como llega de EXIT.

La evidencia se obtiene al abrir la línea desde el endpoint de detalle existente, también para cálculos anteriores que conserven su instantánea. No se vuelve a consultar EXIT ni se incluyen series semanales en todas las filas de las páginas de resultados. No requiere migraciones.
