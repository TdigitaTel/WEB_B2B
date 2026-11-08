"""Durable mail outbox. One message per current ERP destination, never expose a CC list."""
from contextlib import contextmanager
import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from sqlalchemy import select, text
from .db import SessionLocal, engine
from .models import Order, OrderEmailDelivery, OrderTrackingLink
from .customer_order_email import preferences, destinations
from .erp_db import fetch_customer
from .order_email_settings import configuration, cipher, send_message, smtp_diagnostic
from .order_status_email import render_status_email
from . import order_email_events  # Also register listeners in this process.

logger = logging.getLogger(__name__)
LOCK = 731801427


def now():
    return datetime.now(timezone.utc)


def deliver(db, job, contact_reader=None, transport=None, *, manual=False):
    contact_reader = contact_reader or fetch_customer
    transport = transport or send_message
    row, config = configuration(db)
    order = db.get(Order, job.order_id)
    if ((not config.automatic_enabled and not manual) or job.state not in config.selected_states or not order
            or order.deleted_at or order.estado_registro_exit == 'BORRADOR'):
        job.status = 'CANCELLED'; db.commit(); return
    # Superseded pending messages are not useful. Never announce an obsolete state.
    checkpoint = db.get(order_email_events.OrderEmailCheckpoint, order.id)
    if checkpoint and job.revision < checkpoint.revision:
        job.status = 'SUPERSEDED'; db.commit(); return
    selected = preferences(db, order.customer_code)
    if not any(selected.values()):
        job.status = 'CANCELLED'; db.commit(); return
    phase = ['CONTACTS']; password = ''; address = ''
    job.attempts += 1
    try:
        customer = contact_reader(order.customer_code)
        if customer is None:
            raise ValueError('El cliente no está disponible en EXIT')
        recipients = destinations(customer, selected)
        if not recipients:
            job.status = 'NO_RECIPIENT'; job.diagnostic = {'phase': 'CONTACTS', 'response': 'Los campos marcados no contienen correos válidos en EXIT'}; db.commit(); return
        if not row or not row.password_ciphertext or not config.smtp_host or not config.username:
            raise ValueError('Completa la configuración SMTP')
        password = cipher().decrypt(row.password_ciphertext.encode()).decode()
        tracking = config.portal_url
        if config.content.show_link and order.user_id:
            if job.tracking_token_ciphertext:
                token = cipher().decrypt(job.tracking_token_ciphertext.encode()).decode()
            else:
                token = secrets.token_urlsafe(32)
                job.tracking_token_ciphertext = cipher().encrypt(token.encode()).decode()
                db.add(OrderTrackingLink(order_id=order.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                        created_by_user_id=order.user_id, expires_at=now()+timedelta(days=30)))
            tracking = config.portal_url + 'seguimiento#token=' + token
        template = render_status_email(job.payload, tracking, content=config.content)
        completed = set(job.completed_slots or [])
        for recipient in recipients:
            if completed.intersection(recipient['slots']):
                continue
            address = recipient['address']
            message = EmailMessage()
            message['From'] = formataddr((config.sender_name, config.sender_email))
            message['To'] = address
            message['Reply-To'] = config.reply_to
            message['Subject'] = template['subject']
            message['Message-ID'] = f'<order-{job.id}-{recipient["slots"][0]}@webb2b.local>'
            message.set_content(template['text']); message.add_alternative(template['html'], subtype='html')
            # Commit intent before SMTP. A crash after acceptance must not blindly resend.
            job.status = 'SENDING'; db.commit()
            phase[0] = 'CONNECT'
            transport(config, password, message, phase)
            completed.update(recipient['slots'])
            job.completed_slots = sorted(completed); job.status = 'PENDING'; db.commit()
        job.status = 'SENT'; job.diagnostic = None; db.commit()
        logger.info('ORDER_EMAIL_SENT delivery=%s order=%s', job.id, order.public_id)
    except Exception as exc:
        diagnostic = smtp_diagnostic(exc, phase[0], config, password, address)
        job.diagnostic = diagnostic
        # SMTP DATA/network errors can mean accepted mail despite a lost reply.
        # Never auto-retry this ambiguous phase; avoid duplicate customer emails.
        job.status = 'UNCERTAIN' if phase[0] == 'SEND' else 'RETRY' if job.attempts < 5 else 'FAILED'
        job.next_attempt_at = now() + timedelta(seconds=min(3600, 60 * 2**job.attempts))
        db.commit()
        logger.warning('ORDER_EMAIL_FAILED delivery=%s %s', job.id, json.dumps(diagnostic, ensure_ascii=False))


@contextmanager
def delivery_lock():
    # Session-level lock survives commits while sending and drops on process death.
    with engine.connect() as connection:
        acquired=engine.dialect.name!='postgresql' or connection.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':LOCK})
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired and engine.dialect.name=='postgresql':
                connection.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':LOCK});connection.commit()


def run_once():
    with delivery_lock() as acquired:
        if not acquired:return
        with SessionLocal() as db:
            for job in db.scalars(select(OrderEmailDelivery).where(OrderEmailDelivery.status=='SENDING')):
                job.status='UNCERTAIN'
            db.commit()
            jobs=list(db.scalars(select(OrderEmailDelivery).where(
                OrderEmailDelivery.status.in_(['PENDING','RETRY']),
                (OrderEmailDelivery.next_attempt_at.is_(None)) | (OrderEmailDelivery.next_attempt_at<=now())
            ).order_by(OrderEmailDelivery.id).limit(25)))
            for job in jobs:deliver(db,job)


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            run_once()
        except Exception:
            logger.error('ORDER_EMAIL_WORKER_CYCLE_FAILED', exc_info=False)
        time.sleep(10)


if __name__ == '__main__':
    main()
