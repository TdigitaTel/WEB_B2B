# Incidencias logísticas

## Puesta en marcha

1. Integrar en `develop` y desplegar desarrollo. El arranque habitual crea las tablas nuevas; no se requiere una migración manual ni carpetas para archivos.
2. Los operadores activos pueden registrar incidencias en sus delegaciones y atender las tareas que les asigne el flujo. No necesitan permisos generales de atender o autorizar: esa capacidad nace de la asignación de la tarea. En **Accesos de usuarios** solo se configuran dos permisos especiales: **configurar flujos y responsables** y **gestionar procesos autorizados**. Para este último hay que seleccionar procesos ya guardados o «Todos los procesos configurados, incluidos los nuevos». Administración mantiene acceso completo. Los antiguos permisos de registrar/atender/autorizar dejan de ser casillas configurables; no se alteran el estado de las incidencias ni sus responsables. Los gestores antiguos deben elegir su alcance de procesos antes de acceder transversalmente.
3. Abrir **Reposición → Incidencias → Configurar flujos**. Hay modelos iniciales de venta, compra, reposición, inventario e intercambio; inicialmente están desactivados. Configurar responsables, correos y etapas antes de activarlos. También pueden crearse tipos nuevos.
4. Configurar SMTP en Parámetros → Correo. Los avisos de posición utilizan ese transporte, pero se habilitan por tipo de incidencia independientemente de los avisos automáticos de pedidos. Los procesa el worker de correo existente; no hay otro servicio que instalar.

## Registro y atención

El número `INC-año-secuencia` se asigna al registrar la incidencia, mediante un contador transaccional. Es independiente del número de pedido, compra, traslado o toma de inventario. Se guardan delegación, destino cuando corresponda, documento, motivo, descripción, prioridad, fecha necesaria y materiales.

Las bandejas son **Mis tareas**, **Creadas por mí** y **Todas las autorizadas**, con estado, tipo, delegación y número/documento. «Mis tareas» abre por defecto y lista las incidencias registradas por el usuario pendientes de envío, además de las abiertas cuya posición actual está asignada al usuario. Un gestor puede consultar, atender y reasignar incidencias de sus procesos autorizados únicamente en las delegaciones que tiene permitidas; seleccionar todos los procesos no concede acceso a todas las delegaciones. El cierre se asigna al responsable elegido por el configurador. Un configurador sin permiso de gestión no obtiene acceso al contenido de las incidencias de otros. Una asignación del flujo, general o por delegación, permite atender únicamente esa incidencia si su delegación está autorizada, sin ampliar acceso a otras sedes. Se preserva el borrador al alternar entre Incidencias y los cálculos de Reposición.

El solicitante guarda, adjunta y envía. La persona en la posición puede comentar, completar, devolver con motivo o rechazar. El supervisor autorizado puede reasignar, indicando motivo y correo. La asignación al solicitante es una opción del flujo, no una obligación para cerrar. Cada cambio exige la versión vigente para evitar sobrescrituras y queda en el historial. Las incidencias conservan la versión del flujo y las reglas de archivos con las que fueron registradas. Desde el primer borrador, los cambios del flujo requieren una nueva versión para casos nuevos.

Los responsables pueden ser generales o por delegación, con sustituto. Se pueden elegir usuarios web activos sin permisos adicionales de atención, siempre que tengan acceso a la delegación de la actividad. El flujo autoriza la tarea concreta, pero no amplía sus delegaciones. El campo «Actividad» describe el trabajo con nombres genéricos: Registrar, Ejecutar, Autorizar y Cerrar; no representa un permiso global del usuario. Registrar deja constancia de información y comprobaciones; Ejecutar registra la actuación realizada; el documento es obligatorio solo si se configura; Autorizar registra la aprobación para continuar; Cerrar finaliza la incidencia cuando completa la tarea el responsable configurado. Los identificadores de los flujos guardados y sus reglas se conservan, sin migración. Dar permiso de configuración no implica permiso de gestión transversal. RPA no recibe excepciones por su nombre: el alcance se configura igual que para cualquier otro operador. Los intercambios distinguen asignación por origen y por destino. La sustitución se resuelve al entrar en una etapa: si un responsable deja de estar disponible mientras ya tiene el caso, el supervisor debe reasignarlo. Los plazos se muestran en la bandeja; esta versión no genera recordatorios periódicos de vencimiento.

## Inventario

Se pide código, ubicación, unidad, cantidad contada y fecha/hora. Se consulta `UnidadSaldo` de `VIS_EX_StockVentasDelegacion`, con identificación de empresa si está disponible; si no la hay, solo se admite la empresa 1, sin mezclar empresas. Una posición ausente o duplicada requiere revisión; no se inventa un stock cero. La consulta es opcional: el stock puede introducirse o corregirse manualmente, sin justificación adicional. Al guardar desde el formulario se conserva la cifra aportada por el usuario, identificada como manual, sin volver a consultar EXIT.

Ejemplo: sistema 10, contado 5, diferencia −5. Se solicita dejar el material en 5; no se interpreta como una orden ciega de restar cinco. El configurador elige si hay autorización, ejecución y cierre, y su orden. El documento de ejecución y la comprobación del stock actual se exigen solo cuando están marcados en la etapa. Si se registra una comprobación, se consulta el stock actual o se aporta una revisión manual justificada. **No se escribe ni se ajusta stock en EXIT desde estas incidencias.** La ejecución real se realiza en EXIT y aquí se registra su evidencia.

En ventas se pueden importar líneas de un pedido ya disponible en el listado local, respetando delegación y omitiendo líneas eliminadas. Compras y traslados se referencian por su número; no se ha añadido una integración nueva de sus documentos a EXIT.

## Archivos

Cada tipo admite **no recibir**, **opcionales** u **obligatorios antes de enviar**. Las etapas pueden prohibirlos, admitirlos o exigir un archivo nuevo en esa etapa antes de avanzar. Un tipo que no admite archivos no puede habilitarlos desde una etapa.

Se configuran formatos JPG/PNG/WebP/PDF/XLSX, hasta 20 archivos por caso y hasta 8 MB por archivo (inicialmente 10 y 4 MB). El límite del proxy externo puede ser menor; se muestra un error de tamaño si rechaza la subida. Se comprueba extensión, contenido, tamaño y autorización en servidor. Las descargas son autenticadas, como adjunto, sin ejecución en la web. Los archivos quedan como evidencia: no se eliminan desde la ficha. Las imágenes, archivos, flujos e historial se guardan en PostgreSQL y forman parte de su copia de seguridad.

## Avisos y límites de interpretación

Cada entrada o reasignación genera un aviso persistente para el responsable. También se avisa al solicitante al devolverle un borrador. Se muestran cola, aceptación SMTP, errores, configuración pendiente y envíos inciertos. Los avisos de una asignación anterior se sustituyen. No se reintenta automáticamente una entrega incierta tras SMTP DATA. Para repetir un aviso aceptado o incierto se exige un motivo; quien opera debe comprobar antes su recepción. La aceptación SMTP no garantiza entrega en la bandeja del destinatario.

Los enlaces abren la incidencia después de iniciar sesión y vuelven a comprobar permisos. No se envían archivos ni el detalle completo de materiales por correo. No hay actualizaciones periódicas del listado: se carga al entrar, filtrar o actuar, y dispone de Actualizar.

## Compatibilidad de permisos

No se requieren tablas nuevas ni migración manual: la selección de procesos se guarda en la configuración de acceso del usuario. Se conserva la asignación de los casos existentes. Guardar acceso revoca las sesiones como hasta ahora; el usuario debe volver a entrar. Una cuenta habilitada puede trabajar solo en incidencias aunque no tenga otro módulo marcado. El permiso de gestión no se concede automáticamente por marcar «Todas las delegaciones», ni habilita modificar flujos. Si se retira la gestión, se pierde el acceso transversal; las tareas todavía asignadas al usuario siguen siendo su responsabilidad mientras conserve acceso a la delegación.

## Delegaciones autorizadas

Los selectores de origen, destino y configuración muestran solo las delegaciones permitidas en Accesos de usuarios, incluida la sede de referencia. «Todas las delegaciones» mantiene su significado explícito; administración conserva acceso completo. Elegir «Todos los procesos configurados» solo amplía los procesos, nunca las delegaciones.

Se comprueba el alcance también en servidor: listados, detalle, acciones, archivos, asignaciones, reasignaciones y envío de avisos. Un intercambio es visible para usuarios autorizados y relacionados con su origen o destino; para actuar se exige acceso a la delegación de esa actividad (destino en etapas de destino, origen en las demás). Crear o corregir un intercambio exige tener acceso tanto al origen como al destino. Retirar una delegación bloquea los casos fuera del alcance incluso si el usuario los creó o conserva una asignación antigua; los avisos pendientes a responsables sin alcance quedan como no configurados.

La configuración por delegación solo ofrece responsables con acceso a ella. Un responsable general o sustituto también se valida contra la delegación al asignar; si no está habilitado, se utiliza un sustituto válido o se informa de la falta de configuración. Si un flujo compartido tiene asignaciones de otras delegaciones, estas no se muestran y se conservan al guardar las propias. La configuración común y estructura del flujo quedan bloqueadas para el configurador parcial: debe intervenir un configurador con acceso a todas sus delegaciones para cambiarla.

## Listado y edición de flujos

En **Reposición → Incidencias → Configurar flujos** se abre el listado de flujos guardados, con nombre/código, proceso, estado activo o inactivo, número de etapas, delegaciones/asignación y avisos de correo. **Editar** abre una versión sin incidencias con su revisión vigente. Las versiones con incidencias se abren en consulta. **Guardar configuración del flujo** guarda y vuelve al listado; cancelar descarta la edición. El listado muestra la versión vigente y si está bloqueada.

**Nuevo flujo** permite utilizar una plantilla aún no configurada o crear desde cero. Las plantillas iniciales no se cuentan ni se muestran como flujos guardados hasta que se guardan. Se conservan la edición limitada por delegación y el bloqueo de la configuración común de flujos compartidos. El listado se adapta a móvil sin requerir desplazamiento horizontal.

## Actividades y orden definidos por el configurador

El sistema no exige una cadena específica para inventario ni una actividad final de cierre a cargo del solicitante. Se pueden añadir, quitar y reordenar Registrar, Ejecutar, Autorizar y Cerrar; cambiar el tipo de proceso conserva las actividades existentes. Crear desde cero comienza con una sola actividad editable, sin insertar automáticamente una autorización o cierre. Las plantillas son ejemplos modificables.

Cada actividad, incluido Cerrar, puede asignarse al solicitante, a un responsable general o según la delegación; en intercambios también según origen o destino. Completar Cerrar termina la incidencia en esa etapa: no ejecuta las posteriores. Si no hay una actividad Cerrar, completar la última actividad finaliza el proceso. Se mantienen los controles de acceso por delegación, la concurrencia y los requisitos de archivos configurados.

«Exigir documento de resolución» y, en ejecuciones de inventario, «Exigir comprobación del stock actual» son opciones del configurador. Las incidencias antiguas conservan su cierre por el solicitante y sus comprobaciones originalmente obligatorias; al editar el flujo se muestran esas opciones para poder cambiarlas expresamente. No se alteran los flujos capturados en incidencias en curso ni se modifica stock en EXIT.


## Versiones, nombre e historial

Una versión queda bloqueada desde que se registra su primera incidencia, incluido un borrador; las incidencias cerradas también cuentan. No pueden cambiarse las etapas, responsables, archivos, activación ni otras reglas de una versión utilizada. **Nueva versión** copia la definición vigente, exige un motivo y publica la siguiente versión para incidencias nuevas. La versión nueva puede editarse hasta recibir su primera incidencia. Los casos registrados siguen ejecutando su definición original.

**Nombre** permite renombrar el proceso en cualquier momento, sin cambiar su versión ni la definición guardada en los casos. Los listados muestran el nombre actual; la copia histórica conserva el nombre original. **Historial** muestra versiones, actividades, responsables, fecha, autor, motivo de nueva versión y registro de cambios. La revisión técnica para evitar ediciones simultáneas es independiente del número de versión del flujo.

**Eliminar · solo RPA** está disponible únicamente con la identidad real RPA y permiso de configurar flujos. Un administrador o configurador de otra cuenta no puede eliminar, tampoco mediante la API. Además, se exige que el proceso no conserve incidencias sin eliminar en ninguna versión. Las incidencias eliminadas por RPA no bloquean la retirada del proceso; los borradores, abiertas, cerradas o rechazadas que no se hayan eliminado sí la bloquean. La elegibilidad para eliminar se calcula aparte del bloqueo de edición de una versión utilizada. Se retira del listado y de los procesos configurables en permisos, conservando sus versiones y registro de eliminación. El código eliminado queda reservado. Un configurador con alcance parcial no puede eliminar un flujo compartido con otras delegaciones.

El arranque crea las tablas `logistics_incident_flow_versions` y `logistics_incident_flow_changes` y reconstruye versiones de los flujos existentes a partir de las definiciones capturadas en las incidencias. La importación es idempotente, conserva sus reglas de ejecución y marca las versiones como heredadas, sin atribuir un autor de configuración desconocido. Las nuevas incidencias y los cambios de configuración bloquean la misma fila del proceso durante la transacción para evitar registrar casos contra una versión que se esté modificando o eliminando.

## Visor de flujos en curso

En **Reposición → Incidencias → Flujos en curso** el operador ve las incidencias abiertas dentro de sus permisos: número, proceso, versión, delegación, estado, actividad actual, responsable, plazo y progreso de etapas. Permite filtrar por proceso, delegación y número/documento y abrir la ficha. Se carga al entrar o filtrar y dispone de actualización manual; no consulta periódicamente. Los nombres de procesos se cargan en una consulta por página.

El visor aplica el mismo alcance que «Todas las autorizadas»: casos propios, asignados o incluidos en los procesos gestionados, siempre dentro de las delegaciones autorizadas. No concede acceso transversal por ser configurador. La configuración y el historial de versiones requieren el permiso de configurar flujos; registrar y atender incidencias no lo requiere.


## Estado registrado y envío al flujo

Guardar una incidencia deja su número y el estado visible **Registrado · pendiente de envío**. El solicitante dispone de **Enviar al flujo** y **Editar registro** al principio de la ficha. Enviar inicia la primera actividad configurada, asigna a su responsable y genera el aviso correspondiente si está habilitado. El estado previo al envío conserva internamente `DRAFT` para compatibilidad con los registros existentes; no se requiere migración ni se modifica el flujo capturado.

«Mis tareas» incluye tanto los registros propios pendientes de envío como las actividades abiertas asignadas a la cuenta. «Creadas por mí» muestra solo incidencias cuyo solicitante es la cuenta de la sesión y abre con Estado = Todos; alternar bandejas vuelve a la primera página y restablece el filtro de estado adecuado. «Todas las autorizadas» mantiene la consulta transversal según permisos. El listado indica quién es el solicitante y si corresponde a la cuenta actual. Un supervisor no pasa a ser creador ni puede enviar en nombre del solicitante por consultar un registro ajeno; la ficha explica quién tiene pendiente el envío.

**Ubicación en almacén** es la posición física donde se contó el material, por ejemplo pasillo A, estantería 3. No es otra delegación ni una ubicación consultada automáticamente en EXIT. Si el recuento abarca toda la delegación, se puede indicar «Almacén completo». La ayuda aparece junto al campo y el encabezado de la ficha utiliza el mismo nombre.


## Vista visual del flujo y seguimiento

La configuración destaca la cabecera con nombre, versión, estado y número de etapas. El recorrido se muestra mediante círculos conectados con nombre, actividad, responsable previsto y plazo. Pulsar un círculo lleva al editor de esa etapa; el diagrama se actualiza mientras se cambian nombres, actividades, responsables u orden. Las etapas posteriores a Cerrar se marcan como fuera del recorrido. El detalle del editor separa los datos generales de cada etapa y mantiene el bloqueo de versiones utilizadas.

La ficha de una incidencia y el visor «Flujos en curso» muestran el mismo seguimiento visual antes del resto de información: únicamente las etapas configuradas, con la misma numeración del configurador, distinguiendo completadas, etapa actual, pendientes y no ejecutadas. El solicitante y la fecha de registro se presentan aparte, sin añadir una etapa de registro automática. Se muestran fechas de entrada y finalización, responsable real, persona que completó la actividad si fue distinta, plazo actual y responsable previsto de las etapas futuras. Los colores tienen texto y leyenda. En móvil, el recorrido es vertical.

Los datos reales se reconstruyen desde el historial persistido. Las nuevas asignaciones, reasignaciones y finalizaciones incluyen el índice de etapa para distinguir nombres repetidos. Para eventos anteriores se admite el nombre solo cuando identifica una única etapa; las fechas o responsables desconocidos se indican como no registrados. No se sustituyen responsables históricos por los de una versión nueva. Al volver a una etapa se conservan sus entradas anteriores en un desplegable. El resto de actuaciones y comentarios sigue disponible en el historial completo.

La carga del visor consulta eventos y usuarios una sola vez por página, sin consultas por cada etapa ni actualización periódica. No se añade migración ni cambia la lógica de asignación, permisos, envío o avance del flujo.


## Eliminar una incidencia en curso · exclusivo RPA

La cuenta de acceso **RPA**, activa y vinculada a Accesos de usuarios, dispone de la capacidad `incident_delete`. Se determina en servidor por su identificador de acceso, no por el nombre mostrado ni por una casilla que pueda marcarse para otra cuenta. Un administrador genérico tampoco recibe esta capacidad. La identidad RPA mantiene sus límites de delegaciones y procesos; el permiso no concede acceso a incidencias que no puede consultar.

En la ficha de una incidencia registrada o en atención aparece **Eliminar incidencia · solo RPA**. Es necesario escribir el número exacto y un motivo. Se comprueba también la versión para evitar borrar sobre cambios simultáneos. El registro pasa a **Eliminada**, sale de las bandejas normales, pierde su asignación activa y plazo, y se cancelan los avisos en cola o pendientes de reintento. La exclusión se comprueba en servidor: los enlaces antiguos no permiten a otros usuarios consultar, actuar o descargar archivos de la incidencia eliminada.

Se conserva la incidencia, sus archivos, flujo capturado e historial. El evento de eliminación registra usuario, fecha, motivo, estado, etapa y responsable anteriores. RPA puede consultar **Estado → Eliminadas · solo RPA**, incluyendo las que eliminó mientras estaban asignadas a él, dentro de las delegaciones autorizadas. No se elimina el proceso configurado ni sus versiones, no se reutiliza el número de incidencia y no se modifica EXIT. Una versión con incidencias eliminadas sigue bloqueada porque ya fue utilizada.

La eliminación utiliza el mismo bloqueo que el worker de correo para impedir que comience un envío mientras se elimina. Si hay un envío en curso, se informa y se permite reintentar cuando termine; un aviso marcado como SENDING también bloquea la eliminación hasta que el worker resuelva su estado. Los envíos ya realizados y su resultado permanecen en el historial.

No se requiere migración: el estado eliminado y su evidencia utilizan las tablas existentes. No se ha añadido borrado permanente ni cambios automáticos de configuración.


### Datos configurables por actividad

Cada etapa admite hasta 30 datos con nombre, tipo (texto, número o fecha) y obligatoriedad. Se solicitan al responsable de esa etapa, en cualquier actividad, y se validan al completarla tanto en la pantalla como en el servidor. Los campos opcionales pueden quedar vacíos; si se rellenan deben respetar su tipo. No se admiten datos ajenos a la definición guardada de la etapa. Las referencias con letras, guiones o ceros iniciales deben configurarse como texto. Las fechas deben ser fechas reales y los números no admiten NaN ni infinito.

Los valores, sus etiquetas y sus tipos quedan en el evento de finalización junto con la etapa, fecha y usuario. Al devolver una incidencia y atenderla de nuevo se conserva cada actuación anterior. Modificar estos campos en un flujo ya utilizado exige una nueva versión; las incidencias existentes conservan la definición de su versión. Los requisitos anteriores de documento de resolución se mantienen en los flujos que ya los tenían configurados.

En reposición, «Delegación solicitante / destino» identifica dónde se necesita y se recibirá el material. En intercambios se distinguen origen y destino. El documento previo es opcional al registrar una incidencia y no se solicita al crear una reposición nueva: el pedido generado se recoge en la etapa que tenga ese dato configurado, por ejemplo Ejecutar. Para una incidencia sobre una venta o compra ya existente puede indicarse su referencia previa.


### Atención simplificada

El responsable escribe Observaciones y pulsa «Guardar y continuar» o «Guardar y cerrar», según el recorrido configurado. Los datos adicionales solo aparecen si se han configurado para esa etapa. El requisito anterior de documento se presenta como «Número de movimiento»; sigue siendo obligatorio únicamente donde el flujo lo exige. Devolver, rechazar, guardar un comentario sin avanzar y reasignar están agrupados en «Otras acciones». Los archivos opcionales están plegados y los obligatorios se muestran abiertos.

La revisión de stock opcional no muestra controles ni consulta EXIT. Si la versión del flujo exige revisar el stock, se muestra una única casilla «He revisado el stock y los movimientos posteriores al recuento». Al marcarla y completar la etapa queda constancia de una confirmación manual en el historial, sin atribuir una consulta automática a EXIT. Se conserva la validación de esa versión del flujo y no se modifica su configuración ni el historial previo.


### Registro y consultas por campo

En «Formulario de registro», el configurador puede mantener el formulario anterior de materiales/inventario o elegir «Solo los campos configurados». En el segundo modo no se impone código, cantidad, ubicación ni captura de stock: se solicitan exclusivamente los datos definidos, además del contexto de la incidencia (tipo, delegación, motivo, observaciones, prioridad y fecha necesaria). Los datos de registro se definen aparte de los que debe aportar el responsable de cada etapa; no se completan etapas automáticamente al registrar.

Los campos de registro y de etapa se ordenan con ↑ / ↓. «Repetir por línea» permite añadir hasta 100 líneas con los campos configurados, en su orden. Si alguno es obligatorio se exige al menos una línea y se comprueba en todas las líneas aportadas. Los campos únicos aparecen una sola vez. Cada conjunto admite hasta 30 definiciones; se valida tipo, obligatoriedad y ausencia de campos ajenos también en el servidor.

En campos de texto, «Consulta / ayuda → Material de EXIT (lupa)» habilita la búsqueda por código o descripción. Seleccionar un resultado introduce su código, conservando ceros iniciales. «Validar código en EXIT» comprueba los códigos exactos en una única consulta por envío, incluso si se escriben manualmente. Si EXIT falla, la validación no se omite. La búsqueda y validación usan la misma maestra de gestión (incluye materiales inactivos); no consultan ni modifican stock. Sin esa opción no se valida contra EXIT. No se admite SQL libre en la configuración.

Los datos de registro se conservan en los eventos CREATED/CORRECTED; la ficha reconstruye los valores vigentes para consulta y edición, y conserva los anteriores en el historial. Los datos de etapa se guardan en COMPLETED_STAGE. Cada valor conserva nombre, tipo, orden y número de línea. No requiere migración de tablas. Las versiones utilizadas siguen bloqueadas: cambiar orden, consultas o datos exige una nueva versión. Las incidencias anteriores mantienen su formulario y reglas originales.


«Insertar detalle» añade un registro vacío; no se exige buscar material antes de insertarlo. En el formulario configurable aparece únicamente si existen campos marcados como «Campo del detalle (repetible)». Cada detalle ofrece su propia lupa de material y, si está configurado en un campo numérico, «Consultar stock». El configurador debe vincular el campo de stock con un campo de código del mismo detalle; no se toman códigos de otras líneas. La consulta usa la delegación seleccionada y no modifica EXIT. Cambiar el código o la delegación limpia el stock consultado en los campos configurables. El formulario anterior también inserta primero el detalle y desplaza la búsqueda de material a su interior. Los nuevos flujos parten del formulario configurable; las versiones anteriores conservan su modalidad.


Los detalles se presentan en una sola fila con campos compactos. El código de material admite hasta 20 caracteres. Las descripciones extensas pueden configurarse como «Descripción en ventana»; se editan con un botón y se conservan en el mismo registro. En el formulario de inventario anterior, la descripción del material también se edita en una ventana. Si la pantalla es estrecha, la fila permite desplazamiento horizontal.

El stock del sistema siempre puede introducirse manualmente. «Consultar» se sitúa a su derecha y solo sirve de ayuda para copiar el valor de EXIT. No exige marcar una casilla ni justificar la cifra. El formulario envía el stock como aportado por el usuario y al guardar no lo sustituye por una nueva consulta de EXIT; conserva la cifra introducida y calcula la diferencia respecto al contado. Las incidencias y los eventos anteriores no se modifican.
