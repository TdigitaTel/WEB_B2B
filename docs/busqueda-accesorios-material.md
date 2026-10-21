# Búsqueda de accesorios por material

«Accesorios de latón» se interpreta como una pieza de racorería (codo, te, racor, manguito, machón, etc.) cuya información en EXIT contiene latón. No exige la palabra accesorios en cada artículo. También admite cobre, inox, inoxidable, PVC, PPR, PEX, polietileno y acero. Las medidas y demás términos siguen siendo obligatorios. La búsqueda de accesorios sin material y los códigos mantienen la búsqueda habitual.

El cambio se aplica a la consulta de productos y sugerencias que utilizan fetch_catalog_articles. EXIT sigue siendo la única fuente de materiales. Las categorías, filtros de visibilidad y estado activo no cambian. No se exige stock positivo al buscar texto. No requiere renombrar productos.

El reconocimiento se basa en las palabras disponibles en EXIT. No deduce aleaciones por marca o categoría. Si un artículo no indica su material en ningún campo buscable de EXIT, esta mejora no permite atribuírselo automáticamente.


## Parámetros del operador

En Parámetros → Buscador, operadores y administradores pueden activar la ampliación y guardar tres listas: palabras generales, tipos de pieza y materiales. Incluye inicialmente accesorios, piezas, componentes, conexiones, racorería y fittings (con variantes de singular/plural). Separa palabras individuales con comas o saltos de línea. Tildes y mayúsculas se normalizan. Las listas tienen un máximo de 80 palabras y no admiten comodines ni frases. Los cambios afectan a las siguientes consultas de productos y sugerencias sin reiniciar la API.

La configuración se guarda en la nueva tabla PostgreSQL search_settings, creada por el bootstrap habitual al desplegar. Si no hay una configuración guardada, se utilizan los valores predeterminados. GET/PATCH /api/v1/store/search-settings solo permiten acceso a operadores y administradores; cada actualización queda auditada. No modifica datos de EXIT.
