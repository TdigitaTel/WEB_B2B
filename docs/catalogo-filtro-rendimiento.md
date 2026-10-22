# Carga por bloques del filtro de catálogo

El filtro de publicación se aplica en SQL Server mediante tablas temporales de códigos y JOIN/NOT EXISTS antes de COUNT_BIG y OFFSET/FETCH. La clasificación complementaria sigue en PostgreSQL y la maestra comercial sigue siendo EXIT.

La carga de las tablas temporales utilizaba executemany sin tamaño de lote. En pymssql el valor predeterminado depende de arraysize (inicialmente 1), lo que puede enviar una ejecución por código. La nueva función común usa INSERT ... VALUES parametrizado con hasta 1.000 filas por sentencia, tanto para códigos permitidos como excluidos. No crea tablas permanentes ni modifica artículos de EXIT.

La prueba con 25.001 códigos verifica 26 sentencias de inserción y que todos los códigos se envíen exactamente una vez. Se conservan ceros iniciales, se eliminan duplicados y los valores nunca se interpolan como SQL. También se comprueban 0, 1, 999, 1.000 y 1.001 códigos. No se cambia el significado de filtro ausente frente a lista vacía.

Validación: 143 pruebas backend correctas; git diff --check correcto. Sin cambios de esquema ni frontend. No se ha medido la duración en el SQL Server real: validar en desarrollo búsqueda general, por texto, categorías visibles y excluidas y páginas sucesivas.

Referencia del controlador: https://pymssql.readthedocs.io/en/v2.3.2/ref/pymssql.html#pymssql.Cursor.executemany
