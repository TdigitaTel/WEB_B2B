# Reposición: comparación de despacho

Cada línea conserva dos propuestas del mismo objetivo y disponible previsto:

- **Sin agrupación**: necesidad redondeada hacia arriba a unidades enteras.
- **Con múltiplos EXIT**: necesidad redondeada hacia arriba al siguiente `EX_multiplo` positivo válido. Se admiten múltiplos decimales.

No se convierte la unidad del material. Las exclusiones del cálculo se aplican a las dos propuestas. Un múltiplo inexistente o inválido no bloquea la propuesta sin agrupación; la segunda muestra «Revisar múltiplo EXIT» cuando hay necesidad.

Se elimina el selector Formato de despacho. Los cálculos nuevos desde la herramienta usan la propuesta sin agrupación como referencia para contadores, filtros y redistribución; la propuesta agrupada es una alternativa informativa, no una segunda necesidad que se sume.

Almeiras comprueba por separado la suma de cada alternativa para todas las delegaciones incluidas en el cálculo, después de reservar su consumo. No se mezcla ni se reserva stock entre alternativas. Si alguna línea necesaria carece de múltiplo válido, no se confirma cobertura conjunta de la alternativa agrupada.

Ambas propuestas se guardan en la instantánea y se incluyen en el Excel simplificado y ampliado. El ampliado incluye además los totales conjuntos y las comprobaciones de cobertura. Las exportaciones conservan filtros y todas las páginas.

Los cálculos antiguos pueden mostrar ambas cantidades a partir de la necesidad y el múltiplo ya guardados. Si falta la nueva comprobación de cobertura se muestra «Recalcular cobertura». No se modifica su referencia anterior ni sus ajustes manuales: para actualizar la referencia de redistribución se debe recalcular. La API mantiene los parámetros anteriores por compatibilidad con cálculos y clientes existentes.
