# Stock de seguridad opcional

En Cálculo de reposición → Cómo calcular, el selector Stock de seguridad permite elegir Con stock de seguridad (valor inicial) o Sin stock de seguridad. Hay que iniciar un nuevo cálculo para aplicar el cambio.

- Con seguridad: mínimo = consumo diario × plazo de llegada + Z × desviación diaria × raíz del plazo de llegada.
- Sin seguridad: seguridad = 0 y mínimo = consumo diario × plazo de llegada.
- El punto de reposición y el máximo parten de ese mínimo. La reserva propia de Almeiras respeta la misma elección.
- El nivel de servicio se oculta cuando no interviene. Los datos históricos de ventas y desviación no se alteran.

El parámetro `use_safety_stock` se guarda con el cálculo y las políticas JSON existentes, sin migración. Si falta en un cálculo anterior, equivale a `true`. El detalle usa los parámetros del resultado guardado, no los controles de un cálculo todavía pendiente. Los límites manuales explícitos conservan su prioridad. Con seguridad desactivada no se utiliza el percentil alternativo para añadir un colchón implícito.
