"""Avisos de posición con cola persistente; se ejecutan en el worker SMTP existente."""
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from email.utils import formataddr
from sqlalchemy import select
from .models import LogisticsIncident as Incident,IncidentEmail as Mail,User
from .order_email_settings import configuration,cipher,send_message,smtp_diagnostic


def now():return datetime.now(timezone.utc)

def deliver(db,job,transport=None):
    transport=transport or send_message
    row=db.get(Incident,job.incident_id);recipient=db.get(User,job.recipient_id)
    if not row or row.status not in {'DRAFT','OPEN'} or row.assignment_version!=job.assignment_version or row.assignee_id!=job.recipient_id:
        job.status='SUPERSEDED';job.updated_at=now();db.commit();return
    if not recipient or not recipient.active:
        job.status='NOT_CONFIGURED';job.diagnostic={'response':'El responsable ya no tiene acceso activo'};job.updated_at=now();db.commit();return
    if recipient.role not in {'ADMIN','OPERADOR_TIENDA'}:
        job.status='NOT_CONFIGURED';job.diagnostic={'response':'El responsable ya no es un operador activo'};job.updated_at=now();db.commit();return
    saved,config=configuration(db)
    if not saved or not saved.password_ciphertext or not config.smtp_host or not config.username or not job.recipient:
        job.status='NOT_CONFIGURED';job.diagnostic={'response':'Configura el SMTP y el correo del responsable antes de reenviar'};job.updated_at=now();db.commit();return
    phase=['CONFIG'];password='';job.attempts+=1
    try:
        password=cipher().decrypt(saved.password_ciphertext.encode()).decode()
        message=EmailMessage();message['From']=formataddr((config.sender_name,config.sender_email));message['To']=job.recipient;message['Reply-To']=config.reply_to
        message['Subject']=f'{row.number} · {job.stage}'
        message['Message-ID']=f'<incident-{job.id}-{job.assignment_version}@webb2b.local>'
        message.set_content(f'Tienes una incidencia pendiente de atención.\n\n{row.number}\nDelegación: {row.delegation_name}\nTipo: {row.workflow["name"]}\nEtapa: {job.stage}\nDocumento: {row.document or "Sin documento"}\n\nAbre la incidencia en la extranet:\n{config.portal_url}#incident={row.id}\n')
        job.status='SENDING';job.updated_at=now();db.commit()
        transport(config,password,message,phase)
        job.status='SENT';job.diagnostic={'response':'Aceptado por el servidor SMTP. No confirma entrega en bandeja de entrada.'};job.next_attempt_at=None
    except Exception as exc:
        job.diagnostic=smtp_diagnostic(exc,phase[0],config,password,job.recipient)
        job.status='UNCERTAIN' if phase[0]=='SEND' else 'RETRY' if job.attempts<5 else 'FAILED'
        job.next_attempt_at=now()+timedelta(seconds=min(3600,60*2**job.attempts))
    job.updated_at=now();db.commit()


def run_pending(db):
    # Called under the order worker's session-level advisory lock, including SMTP commits.
    for job in db.scalars(select(Mail).where(Mail.status=='SENDING')):
        job.status='UNCERTAIN';job.updated_at=now();job.diagnostic={'response':'El proceso se interrumpió durante el envío; comprueba antes de reenviar'}
    db.commit()
    jobs=list(db.scalars(select(Mail).where(Mail.status.in_(['PENDING','RETRY']),or_due()).order_by(Mail.id).limit(25)))
    for job in jobs:deliver(db,job)


def or_due():return (Mail.next_attempt_at.is_(None)) | (Mail.next_attempt_at<=now())
