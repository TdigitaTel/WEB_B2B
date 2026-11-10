"""Operator-safe, immutable dispatch history. Never store message bodies or credentials."""
from .models import AuditEvent

STATUS_LABELS={'PENDING':'En cola','QUEUED':'En cola','SENDING':'Enviando','SENT':'Aceptado por SMTP',
    'RECIPIENT_ACCEPTED':'Destinatario aceptado por SMTP','RETRY':'Error · reintento pendiente',
    'FAILED':'Error de envío','UNCERTAIN':'Resultado sin confirmar','CANCELLED':'Cancelado',
    'SUPERSEDED':'Sustituido por un estado posterior','NO_RECIPIENT':'Sin destinatarios válidos',
    'SKIPPED':'Aviso no generado'}
DIAGNOSTIC_FIELDS=('phase','exception','smtp_code','response','reference','code')


def safe_diagnostic(value):
    return {key:value[key] for key in DIAGNOSTIC_FIELDS if key in value} if isinstance(value,dict) else None


def record(db,order,state,status,*,job=None,mode='AUTOMATIC',reason=None,diagnostic=None,slots=None,revision=None):
    if order is None:return
    db.add(AuditEvent(action='ORDER_EMAIL_LOG',entity_type='ORDER',entity_id=order.public_id,
        metadata_json={'state':state,'status':status,'mode':mode,'reason':reason,
            'delivery_id':job.id if job else None,'revision':job.revision if job else revision,
            'attempt':(job.attempts or 0) if job else 0,'diagnostic':safe_diagnostic(diagnostic),
            'completed_slots':list(slots if slots is not None else (job.completed_slots or []) if job else [])}))
