# Incidencias logísticas

## Puesta en marcha

1. Integrar en `develop` y desplegar desarrollo. El arranque habitual crea las tablas nuevas; no se requiere una migración manual ni carpetas para archivos.
2. Los operadores activos pueden registrar incidencias en sus delegaciones y atender las tareas que les asigne el flujo. No necesitan permisos generales de atender o autorizar: esa capacidad nace de la asignación de la tarea. En **Accesos de usuarios** solo se configuran dos permisos especiales: **configurar flujos y responsables** y **gestionar procesos autorizados**. Para este último hay que seleccionar procesos ya guardados o «Todos los procesos configurados, incluidos los nuevos». Administración mantiene acceso completo. Los antiguos permisos de registrar/atender/autorizar dejan de ser casillas configurables; no se alteran el estado de las incidencias ni sus responsables. Los gestores antiguos deben elegir su alcance de procesos antes de acceder transversalmente.
3. Abrir **Reposición → Incidencias → Configurar flujos**. Hay modelos iniciales de venta, compra, reposición, inventario e intercambio; inicialmente están desactivados. Configurar responsables, correos y etapas antes de activarlos. También pueden crearse tipos nuevos.
4. Configurar SMTP en Parámetros → Correo. Los avisos de posición utilizan ese transporte, pero se habilitan por tipo de incidencia independientemente de los avisos automáticos de pedidos. Los procesa el worker de correo existente; no hay otro servicio que instalar.

## Registro y atención

El número `INC-año-secuencia` se asigna al guardar el borrador, mediante un contador transaccional. Es independiente del número de pedido, compra, traslado o toma de inventario. Se guardan delegación, destino cuando corresponda, documento, motivo, descripción, prioridad, fecha necesaria y materiales.

Las bandejas son **Mis tareas**, **Creadas por mí** y **Todas las autorizadas**, con estado, tipo, delegación y número/documento. «Mis tareas» abre por defecto y lista las incidencias abiertas cuya posición actual está asignada al usuario. Un gestor puede consultar, atender y reasignar incidencias de sus procesos autorizados únicamente en las delegaciones que tiene permitidas; seleccionar todos los procesos no concede acceso a todas las delegaciones. El cierre se asigna al responsable elegido por el configurador. Un configurador sin permiso de gestión no obtiene acceso al contenido de las incidencias de otros. Una asignación del flujo, general o por delegación, permite atender únicamente esa incidencia si su delegación está autorizada, sin ampliar acceso a otras sedes. Se preserva el borrador al alternar entre Incidencias y los cálculos de Reposición.

El solicitante guarda, adjunta y envía. La persona en la posición puede comentar, completar, devolver con motivo o rechazar. El supervisor autorizado puede reasignar, indicando motivo y correo. La asignación al solicitante es una opción del flujo, no una obligación para cerrar. Cada cambio exige la versión vigente para evitar sobrescrituras y queda en el historial. Las incidencias en curso conservan el flujo y las reglas de archivos con los que fueron creadas; editar la configuración se aplica a casos nuevos.

Los responsables pueden ser generales o por delegación, con sustituto. Se pueden elegir usuarios web activos sin permisos adicionales de atención, siempre que tengan acceso a la delegación de la actividad. El flujo autoriza la tarea concreta, pero no amplía sus delegaciones. El campo «Actividad» describe el trabajo con nombres genéricos: Registrar, Ejecutar, Autorizar y Cerrar; no representa un permiso global del usuario. Registrar deja constancia de información y comprobaciones; Ejecutar registra la actuación realizada; el documento es obligatorio solo si se configura; Autorizar registra la aprobación para continuar; Cerrar finaliza la incidencia cuando completa la tarea el responsable configurado. Los identificadores de los flujos guardados y sus reglas se conservan, sin migración. Dar permiso de configuración no implica permiso de gestión transversal. RPA no recibe excepciones por su nombre: el alcance se configura igual que para cualquier otro operador. Los intercambios distinguen asignación por origen y por destino. La sustitución se resuelve al entrar en una etapa: si un responsable deja de estar disponible mientras ya tiene el caso, el supervisor debe reasignarlo. Los plazos se muestran en la bandeja; esta versión no genera recordatorios periódicos de vencimiento.

## Inventario

Se pide código, ubicación, unidad, cantidad contada y fecha/hora. Se consulta `UnidadSaldo` de `VIS_EX_StockVentasDelegacion`, con identificación de empresa si está disponible; si no la hay, solo se admite la empresa 1, sin mezclar empresas. Una posición ausente o duplicada requiere revisión; no se inventa un stock cero. Al guardar se vuelve a capturar el valor. Si EXIT no está disponible, se puede aportar stock manual con justificación y queda marcado como manual.

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

En **Reposición → Incidencias → Configurar flujos** se abre el listado de flujos guardados, con nombre/código, proceso, estado activo o inactivo, número de etapas, delegaciones/asignación y avisos de correo. **Editar** abre el flujo seleccionado con su revisión vigente. **Guardar configuración del flujo** guarda y vuelve al listado; cancelar descarta la edición. Los cambios siguen aplicándose a nuevas incidencias, sin modificar los flujos capturados en los casos en curso.

**Nuevo flujo** permite utilizar una plantilla aún no configurada o crear desde cero. Las plantillas iniciales no se cuentan ni se muestran como flujos guardados hasta que se guardan. Se conservan la edición limitada por delegación y el bloqueo de la configuración común de flujos compartidos. El listado se adapta a móvil sin requerir desplazamiento horizontal.

## Actividades y orden definidos por el configurador

El sistema no exige una cadena específica para inventario ni una actividad final de cierre a cargo del solicitante. Se pueden añadir, quitar y reordenar Registrar, Ejecutar, Autorizar y Cerrar; cambiar el tipo de proceso conserva las actividades existentes. Crear desde cero comienza con una sola actividad editable, sin insertar automáticamente una autorización o cierre. Las plantillas son ejemplos modificables.

Cada actividad, incluido Cerrar, puede asignarse al solicitante, a un responsable general o según la delegación; en intercambios también según origen o destino. Completar Cerrar termina la incidencia en esa etapa: no ejecuta las posteriores. Si no hay una actividad Cerrar, completar la última actividad finaliza el proceso. Se mantienen los controles de acceso por delegación, la concurrencia y los requisitos de archivos configurados.

«Exigir documento de resolución» y, en ejecuciones de inventario, «Exigir comprobación del stock actual» son opciones del configurador. Las incidencias antiguas conservan su cierre por el solicitante y sus comprobaciones originalmente obligatorias; al editar el flujo se muestran esas opciones para poder cambiarlas expresamente. No se alteran los flujos capturados en incidencias en curso ni se modifica stock en EXIT.
