# Equivalencias de medidas editables

En **Parámetros → Buscador y sinónimos → Medidas**, el operador puede añadir una medida numérica y sus equivalencias, editarlas o quitar filas. Por ejemplo: medida `1/2`, equivalencias `media, medio, mitad`. Se guardan con los materiales y las palabras generales mediante **Guardar reglas del buscador**. **Probar búsqueda** muestra el texto interpretado y sus condiciones; admite el ejemplo «piezas inoxidable de media».

Las filas se almacenan en `search_settings.config.measure_equivalences` como una lista de `{value, aliases}`. Se aplican al catálogo, las sugerencias, el probador y la consulta local de productos. No hay sustituciones fijas de «media», «cuarto» ni «tres cuartos» en el normalizador. Sin filas, esas palabras permanecen literales.

El normalizador conserva las reglas sintácticas comunes (minúsculas, tildes, espacios de fracciones, comillas y palabras de enlace). Las equivalencias configuradas se aplican por palabras o frases completas, primero las más largas y en una sola pasada. Se rechazan medidas repetidas, equivalencias asignadas a dos medidas, comodines y fracciones con denominador cero.

La primera ejecución de `bootstrap` copia las equivalencias anteriores desde el archivo de datos iniciales `app/data/search_measure_equivalences.json` a la configuración de la BD. Esta carga solo ocurre cuando falta el campo. No cambia materiales ni otras reglas. Una lista vacía o cualquier modificación posterior se respeta en siguientes arranques. El PATCH antiguo que omite el campo conserva las medidas guardadas.

No requiere tablas ni dependencias nuevas. La funcionalidad se activa al desplegar y ejecutar el bootstrap habitual. Validación local: persistencia, migración repetida, eliminación sin restauración, ambigüedades, catálogo y sugerencias con la misma interpretación, permisos y edición/cambio de pestañas en React.
