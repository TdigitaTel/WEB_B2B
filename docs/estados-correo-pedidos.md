# Estados del correo de pedidos

La selección de avisos y el editor de mensajes muestran los mismos siete estados del seguimiento: Pendiente, En procesamiento, Pendiente de recogida parcial/total, Entregado parcial/total y Facturado. Los parciales son subestados, no etapas adicionales. Se mantiene la clave interna EN_PREPARACION por compatibilidad con la configuración guardada.

Pendiente confirma la recepción del pedido. Un resumen de preparación vacío no lo sustituye por En procesamiento. Su aviso inicial permanece en cola aunque comience la gestión antes de que el trabajador de correo lo procese. Sigue respetando activación, estados seleccionados, destinatarios marcados, cancelación y registro de envíos para evitar duplicados. Los avisos históricos no se generan al activar la función.

«No se va a atender» era una etiqueta interna para pedidos confirmados como inexistentes en EXIT. Se retira de las opciones de comunicación y del editor. Las configuraciones antiguas se leen sin esa selección, conservando conexión SMTP y textos. No se envía el aviso pendiente de un pedido ya retirado. El registro interno y la trazabilidad no se eliminan.
