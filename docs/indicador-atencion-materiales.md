# Atención parcial de materiales

El indicador adicional aparece junto al estado del pedido en las listas del operador y del cliente, y en el seguimiento compartido. No modifica el estado procedente de EXIT ni marca entregas.

Se cuentan líneas de material activas, sin sumar unidades de artículos diferentes. Una línea se considera atendida cuando su cantidad servida cubre toda la cantidad pedida. Una línea parcialmente servida sigue contando como pendiente. Ejemplo: de cinco líneas activas, cuatro completas y una pendiente resulta «Atendido al 80% · Falta 1 material».

Las líneas eliminadas en EXIT se excluyen tanto del total como de las atendidas y pendientes, incluso si antes estuvieron servidas. Si reaparecen, vuelven a participar. Sin líneas activas se muestra «Sin materiales activos», sin atribuir un 100%. El porcentaje entero se redondea hacia abajo para no mostrar 100% mientras falten materiales.

Es un dato derivado de las líneas ya consultadas: no necesita nuevos campos ni consultas adicionales y sigue el refresco de la lista.
