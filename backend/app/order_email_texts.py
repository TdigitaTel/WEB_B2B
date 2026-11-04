"""Editable starter suggestions; never required customer copy."""
STATES = {
    'PENDIENTE': 'Pedido recibido', 'EN_PREPARACION': 'En preparación',
    'PENDIENTE_RECOGIDA_PARCIAL': 'Pendiente de recogida parcial',
    'PENDIENTE_RECOGIDA_TOTAL': 'Pendiente de recogida total',
    'ENTREGADO_PARCIAL': 'Entregado parcial', 'ENTREGADO_TOTAL': 'Entregado total',
    'FACTURADO': 'Facturado', 'ELIMINADO_EN_EXIT': 'No se va a atender',
}
MESSAGES = {
    'PENDIENTE': 'Hemos recibido tu pedido. Te avisaremos cuando haya materiales disponibles para recoger.',
    'EN_PREPARACION': 'Estamos preparando tu pedido. Te avisaremos cuando puedas recoger materiales.',
    'PENDIENTE_RECOGIDA_PARCIAL': 'Ya puedes recoger parte de tu pedido. Te avisaremos cuando esté disponible lo pendiente.',
    'PENDIENTE_RECOGIDA_TOTAL': 'Ya puedes recoger todos los materiales pendientes de tu pedido.',
    'ENTREGADO_PARCIAL': 'Has recogido parte de tu pedido. Consulta el seguimiento para conocer el avance de los materiales pendientes.',
    'ENTREGADO_TOTAL': 'La recogida de tu pedido está completa.',
    'FACTURADO': 'Tu pedido ha sido facturado. Consulta el seguimiento para comprobar si quedan materiales pendientes de recoger.',
    'ELIMINADO_EN_EXIT': 'Este pedido no va a atenderse. Si necesitas ayuda, responde a este correo.',
    'REVISAR_ENTREGA_HISTORICA': 'Estamos revisando el desglose de una entrega anterior. Consulta el seguimiento para ver la información disponible.',
    'SIN_MATERIALES_ACTIVOS': 'El pedido no tiene materiales activos. Consulta su seguimiento para ver el detalle.',
    'PENDIENTE_RECOGIDA': 'Hay materiales disponibles para recoger. Consulta el seguimiento para ver el detalle.',
    'EN_GESTION': 'Estamos gestionando tu pedido. Te avisaremos cuando haya novedades.',
}
LABELS = {**STATES, 'REVISAR_ENTREGA_HISTORICA': 'Entrega en revisión',
          'SIN_MATERIALES_ACTIVOS': 'Sin materiales activos', 'EN_GESTION': 'En gestión',
          'PENDIENTE_RECOGIDA': 'Pendiente de recogida'}
ALIASES = {'REGISTRADO': 'EN_PREPARACION', 'EN_PROCESO': 'EN_PREPARACION',
           'EN_PROCESAMIENTO': 'EN_PREPARACION', 'BLOQUEADO': 'EN_GESTION',
           'ATENDIDO': 'PENDIENTE_RECOGIDA', 'PENDIENTE_RECOJO': 'PENDIENTE_RECOGIDA',
           'ENTREGADO': 'ENTREGADO_TOTAL'}

