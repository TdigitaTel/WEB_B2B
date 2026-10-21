# Búsqueda de accesorios por material

«Accesorios de latón», «piezas de latón» y «componentes de latón» se consultan igual que «latón»: se omite la palabra genérica y se conservan el material y los demás términos. Puede devolver cualquier artículo de ese material, aunque no sea una pieza de racorería. El texto escrito permanece visible en la web. También admite cobre, inox, inoxidable, PVC, PPR, PEX, polietileno y acero. Las medidas y demás términos siguen siendo obligatorios. La búsqueda de accesorios sin material y los códigos mantienen la búsqueda habitual.

El cambio se aplica a la consulta de productos y sugerencias que utilizan fetch_catalog_articles. EXIT sigue siendo la única fuente de materiales. Las categorías, filtros de visibilidad y estado activo no cambian. No se exige stock positivo al buscar texto. No requiere renombrar productos.

El reconocimiento se basa en las palabras disponibles en EXIT. No deduce aleaciones por marca o categoría. Si un artículo no indica su material en ningún campo buscable de EXIT, esta mejora no permite atribuírselo automáticamente.


## Parámetros del operador

En Parámetros → Buscador, operadores y administradores pueden activar la simplificación y guardar dos listas: palabras generales y materiales. La lista histórica `piece_names` se conserva en la API y en los datos por compatibilidad, pero ya no se utiliza para filtrar ni se edita en la pantalla. Incluye inicialmente accesorios, piezas, componentes, conexiones, racorería y fittings (con variantes de singular/plural). Separa palabras individuales con comas o saltos de línea. Tildes y mayúsculas se normalizan. Las listas tienen un máximo de 80 palabras y no admiten comodines ni frases. Los cambios afectan a las siguientes consultas de productos y sugerencias sin reiniciar la API.

La configuración se guarda en la nueva tabla PostgreSQL search_settings, creada por el bootstrap habitual al desplegar. Si no hay una configuración guardada, se utilizan los valores predeterminados. GET/PATCH /api/v1/store/search-settings solo permiten acceso a operadores y administradores; cada actualización queda auditada. No modifica datos de EXIT.

## Rendimiento

La consulta de material utiliza el mismo SQL y los mismos parámetros con o sin las palabras genéricas reconocidas. Se elimina la expansión de tipos de pieza con decenas de `LIKE` y transformaciones `REPLACE`, tanto del conteo como de la página. No añade campos, índices ni modificaciones en EXIT o PostgreSQL. La mejora de tiempo real debe medirse en desarrollo/producción; esta modificación no garantiza una duración específica.
