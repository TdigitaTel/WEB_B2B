# Incidencias logísticas

## Puesta en marcha

1. Integrar en `develop` y desplegar desarrollo. El arranque habitual crea las tablas nuevas; no se requiere una migración manual ni carpetas para archivos.
2. Los operadores activos pueden registrar incidencias en sus delegaciones y atender las tareas que les asigne el flujo. No necesitan permisos generales de atender o autorizar: esa capacidad nace de la asignación de la tarea. En **Accesos de usuarios** solo se configuran dos permisos especiales: **configurar flujos y responsables** y **gestionar procesos autorizados**. Para este último hay que seleccionar procesos ya guardados o «Todos los procesos configurados, incluidos los nuevos». Administración mantiene acceso completo. Los antiguos permisos de registrar/atender/autorizar dejan de ser casillas configurables; no se alteran el estado de las incidencias ni sus responsables. Los gestores antiguos deben elegir su alcance de procesos antes de acceder transversalmente.
3. Abrir **Reposición → Incidencias → Configurar flujos**. Hay modelos iniciales de venta, compra, reposición, inventario e intercambio; inicialmente están desactivados. Configurar responsables, correos y etapas antes de activarlos. También pueden crearse tipos nuevos.
4. Configurar SMTP en Parámetros → Correo. Los avisos de posición utilizan ese transporte, pero se habilitan por tipo de incidencia independientemente de los avisos automáticos de pedidos. Los procesa el worker de correo existente; no hay otro servicio que instalar.

## Registro y atención

El número `INC-año-secuencia` se asigna al guardar el borrador, mediante un contador transaccional. Es independiente del número de pedido, compra, traslado o toma de inventario. Se guardan delegación, destino cuando corresponda, documento, motivo, descripción, prioridad, fecha necesaria y materiales.

Las bandejas son **Mis tareas**, **Creadas por mí** y **Todas las autorizadas**, con estado, tipo, delegación y número/documento. «Mis tareas» abre por defecto y lista las incidencias abiertas cuya posición actual está asignada al usuario. Un gestor puede consultar, atender y reasignar incidencias de sus procesos autorizados en cualquier delegación; no obtiene acceso a los demás procesos por esa condición. La confirmación final sigue correspondiendo al solicitante. Un configurador sin permiso de gestión no obtiene acceso al contenido de las incidencias de otros. Una asignación del flujo, general o por delegación, permite atender únicamente esa incidencia, sin abrir el resto de incidencias ni las operaciones de otras sedes. Se preserva el borrador al alternar entre Incidencias y los cálculos de Reposición.

El solicitante guarda, adjunta y envía. La persona en la posición puede comentar, completar, devolver con motivo o rechazar. El supervisor autorizado puede reasignar, indicando motivo y correo. La confirmación final corresponde al solicitante. Cada cambio exige la versión vigente para evitar sobrescrituras y queda en el historial. Las incidencias en curso conservan el flujo y las reglas de archivos con los que fueron creadas; editar la configuración se aplica a casos nuevos.

Los responsables pueden ser generales o por delegación, con sustituto. Se pueden elegir usuarios web activos sin permisos adicionales de atención ni restricciones de su sede habitual: es el flujo el que autoriza la tarea concreta. El campo «Actividad» describe el trabajo con nombres genéricos: Registrar, Ejecutar, Autorizar y Cerrar; no representa un permiso global del usuario. Registrar deja constancia de información y comprobaciones; Ejecutar registra la actuación realizada y su documento; Autorizar registra la aprobación para continuar; Cerrar recoge la confirmación final del solicitante. Los identificadores de los flujos guardados y sus reglas se conservan, sin migración. Dar permiso de configuración no implica permiso de gestión transversal. RPA no recibe excepciones por su nombre: el alcance se configura igual que para cualquier otro operador. Los intercambios distinguen asignación por origen y por destino. La sustitución se resuelve al entrar en una etapa: si un responsable deja de estar disponible mientras ya tiene el caso, el supervisor debe reasignarlo. Los plazos se muestran en la bandeja; esta versión no genera recordatorios periódicos de vencimiento.

## Inventario

Se pide código, ubicación, unidad, cantidad contada y fecha/hora. Se consulta `UnidadSaldo` de `VIS_EX_StockVentasDelegacion`, con identificación de empresa si está disponible; si no la hay, solo se admite la empresa 1, sin mezclar empresas. Una posición ausente o duplicada requiere revisión; no se inventa un stock cero. Al guardar se vuelve a capturar el valor. Si EXIT no está disponible, se puede aportar stock manual con justificación y queda marcado como manual.

Ejemplo: sistema 10, contado 5, diferencia −5. Se solicita dejar el material en 5; no se interpreta como una orden ciega de restar cinco. El flujo debe contener autorización antes de ejecución. Al completar la ejecución se pide documento de ajuste y comprobación de movimientos posteriores; se vuelve a consultar el stock actual o se registra una comprobación manual justificada. **No se escribe ni se ajusta stock en EXIT desde estas incidencias.** La ejecución real se realiza en EXIT y aquí se registra su evidencia.

En ventas se pueden importar líneas de un pedido ya disponible en el listado local, respetando delegación y omitiendo líneas eliminadas. Compras y traslados se referencian por su número; no se ha añadido una integración nueva de sus documentos a EXIT.

## Archivos

Cada tipo admite **no recibir**, **opcionales** u **obligatorios antes de enviar**. Las etapas pueden prohibirlos, admitirlos o exigir un archivo nuevo en esa etapa antes de avanzar. Un tipo que no admite archivos no puede habilitarlos desde una etapa.

Se configuran formatos JPG/PNG/WebP/PDF/XLSX, hasta 20 archivos por caso y hasta 8 MB por archivo (inicialmente 10 y 4 MB). El límite del proxy externo puede ser menor; se muestra un error de tamaño si rechaza la subida. Se comprueba extensión, contenido, tamaño y autorización en servidor. Las descargas son autenticadas, como adjunto, sin ejecución en la web. Los archivos quedan como evidencia: no se eliminan desde la ficha. Las imágenes, archivos, flujos e historial se guardan en PostgreSQL y forman parte de su copia de seguridad.

## Avisos y límites de interpretación

Cada entrada o reasignación genera un aviso persistente para el responsable. También se avisa al solicitante al devolverle un borrador. Se muestran cola, aceptación SMTP, errores, configuración pendiente y envíos inciertos. Los avisos de una asignación anterior se sustituyen. No se reintenta automáticamente una entrega incierta tras SMTP DATA. Para repetir un aviso aceptado o incierto se exige un motivo; quien opera debe comprobar antes su recepción. La aceptación SMTP no garantiza entrega en la bandeja del destinatario.

Los enlaces abren la incidencia después de iniciar sesión y vuelven a comprobar permisos. No se envían archivos ni el detalle completo de materiales por correo. No hay actualizaciones periódicas del listado: se carga al entrar, filtrar o actuar, y dispone de Actualizar.

## Compatibilidad de permisos

No se requieren tablas nuevas ni migración manual: la selección de procesos se guarda en la configuración de acceso del usuario. Se conserva la asignación de los casos existentes. Guardar acceso revoca las sesiones como hasta ahora; el usuario debe volver a entrar. Una cuenta habilitada puede trabajar solo en incidencias aunque no tenga otro módulo marcado. El permiso de gestión no se concede automáticamente por marcar «Todas las delegaciones», ni habilita modificar flujos. Si se retira la gestión, se pierde el acceso transversal; las tareas todavía asignadas al usuario siguen siendo su responsabilidad.
