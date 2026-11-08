# Histórico en la información de cada material

En Reposición, abrir el código del material o «Ver datos» muestra:

- Mediana del consumo diario: valor central de los días ordenados (promedio de los dos centrales si hay un número par de días).
- Moda del consumo diario: todos los valores con la máxima frecuencia. Si ningún valor se repite, se muestra «Sin moda».
- Gráfico de ventas brutas por semanas de lunes a domingo, con los máximos destacados y una tabla desplegable con cantidades exactas, devoluciones y consumo acumulado.

Las estadísticas corresponden al artículo y delegación de esa línea y a la instantánea guardada del cálculo. Incluyen días sin ventas y usan consumo diario = máximo entre cero y ventas menos devoluciones, igual que la desviación del motor. El rango efectivo respeta tanto las fechas seleccionadas como el límite de histórico o el alta del artículo cuando sean aplicables. Las semanas de los extremos solo incluyen los días dentro del rango; no se extrapolan.

Estos indicadores son informativos: no sustituyen el promedio ni modifican el stock de seguridad o la cantidad propuesta. La unidad se conserva tal como llega de EXIT.

La evidencia se obtiene al abrir la línea desde el endpoint de detalle existente, también para cálculos anteriores que conserven su instantánea. No se vuelve a consultar EXIT ni se incluyen series semanales en todas las filas de las páginas de resultados. No requiere migraciones.
