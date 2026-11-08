"""Operator-triggered delivery of the current order state, with the same mail outbox."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import require_roles, audit
from .db import get_db
from .models import OrderEmailCheckpoint, OrderEmailDelivery
from .order_email_events import snapshot
from .order_email_settings import configuration
from .order_email_texts import LABELS, STATES
from .customer_order_email import preferences, destinations
from .order_email_worker import deliver, delivery_lock

router=APIRouter(prefix='/api/v1/store/orders',tags=['Correo de pedidos'])
operator=require_roles('OPERADOR_TIENDA','ADMIN')


def scoped_order(db,user,order_id):
    from .main import operator_web_order
    return operator_web_order(db,order_id,user)


def inspect(db,order):
    key,state,payload=snapshot(db,order)
    row,config=configuration(db)
    checkpoint=db.get(OrderEmailCheckpoint,order.id,populate_existing=True)
    job=db.scalar(select(OrderEmailDelivery).where(OrderEmailDelivery.order_id==order.id,
            OrderEmailDelivery.revision==checkpoint.revision)) if checkpoint and checkpoint.state==key else None
    result={'state_key':key,'state_label':LABELS.get(state,state),'can_send':False,'reason':'',
            'status':job.status if job else None,'requires_confirmation':bool(job and job.status in {'UNCERTAIN','SENDING'}),
            'recipient_count':0,'automatic_enabled':config.automatic_enabled,
            'diagnostic':job.diagnostic if job else None}
    if order.deleted_at or order.estado_registro_exit=='BORRADOR':
        result['reason']='Este pedido todavía no está disponible para enviar avisos.'
    elif state not in config.selected_states:
        result['reason']=f'El estado «{result["state_label"]}» no está configurado para enviar correos. '+('Actívalo en Parámetros → Correo de pedidos.' if state in STATES else 'No hay un aviso disponible para este estado; revisa el estado del pedido.')
    elif job and job.status=='SENT':
        result['reason']='El servidor de correo ya aceptó el aviso de este estado. Comprueba la bandeja de entrada y correo no deseado.'
    elif not row or not row.password_ciphertext or not config.smtp_host or not config.username:
        result['reason']='El envío de correos no está configurado. Revisa servidor, usuario y contraseña en Parámetros → Correo de pedidos.'
    elif not order.customer_code or not any(preferences(db,order.customer_code).values()):
        result['reason']='No hay correos destino marcados en la ficha del cliente. Marca Email1 o Email2 para recibir avisos de estado.'
    else:
        from .main import fetch_customer
        try:
            customer=fetch_customer(order.customer_code)
        except Exception:
            raise HTTPException(503,'No se pudieron comprobar los correos actuales en EXIT. Inténtalo de nuevo') from None
        recipients=destinations(customer or {},preferences(db,order.customer_code))
        result['recipient_count']=len(recipients)
        if not recipients:
            result['reason']='Los campos marcados del cliente no contienen correos válidos en EXIT.'
        else:
            result['can_send']=True
            result['reason']=('El envío anterior no está confirmado. Podría haberse aceptado; comprueba el correo antes de reintentarlo.'
                              if result['requires_confirmation'] else 'Se enviará el aviso del estado actual a los correos marcados del cliente.')
    return result,job,checkpoint,state,payload


@router.get('/{order_id}/email')
def email_status(order_id:str,db:Session=Depends(get_db),user=Depends(operator)):
    return inspect(db,scoped_order(db,user,order_id))[0]


class Resend(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_state_key:str=Field(min_length=1,max_length=120)
    confirm_uncertain:StrictBool=False


@router.post('/{order_id}/email/resend')
def resend(order_id:str,data:Resend,db:Session=Depends(get_db),user=Depends(operator)):
    # Same session lock as the worker: no parallel sending or double-click duplicates.
    with delivery_lock() as acquired:
        if not acquired:
            raise HTTPException(409,'Hay otro envío de correo en curso. Espera unos segundos y vuelve a intentarlo.')
        order=scoped_order(db,user,order_id)
        status,job,checkpoint,state,payload=inspect(db,order)
        if data.expected_state_key!=status['state_key']:
            raise HTTPException(409,'El estado del pedido ha cambiado. Revisa el estado actual antes de reenviar el correo.')
        if not status['can_send']:
            raise HTTPException(409,status['reason'])
        if status['requires_confirmation'] and not data.confirm_uncertain:
            raise HTTPException(409,'El envío anterior no está confirmado. Confirma que quieres reintentarlo antes de continuar.')
        if checkpoint is None:
            checkpoint=OrderEmailCheckpoint(order_id=order.id,state=status['state_key'],revision=1);db.add(checkpoint)
        elif checkpoint.state!=status['state_key']:
            checkpoint.state=status['state_key'];checkpoint.revision+=1
        if job is None:
            job=OrderEmailDelivery(order_id=order.id,revision=checkpoint.revision,state=state,payload=payload);db.add(job)
        else:
            # Retain completed destinations: a partial SMTP failure must not resend those already accepted.
            job.payload=payload;job.state=state;job.status='PENDING';job.next_attempt_at=None;job.attempts=0
        audit(db,user,'ORDER_EMAIL_MANUAL_REQUESTED','ORDER',order.public_id,{'state':state,'confirmed_uncertain':data.confirm_uncertain})
        db.commit()
        from .main import fetch_customer
        deliver(db,job,contact_reader=fetch_customer,manual=True)
        if job.status=='SENT':
            audit(db,user,'ORDER_EMAIL_MANUAL_ACCEPTED','ORDER',order.public_id,{'state':state,'delivery_id':job.id});db.commit()
            return {'message':'El servidor de correo ha aceptado el aviso del estado actual. Comprueba la bandeja de entrada y correo no deseado.',
                    'status':'SENT','can_send':False,'state_key':status['state_key'],'state_label':status['state_label'],
                    'reason':'Aviso aceptado por el servidor de correo.','requires_confirmation':False,'recipient_count':status['recipient_count']}
        diagnostic=job.diagnostic or {}
        detail=('No se ha confirmado el envío del correo. '+
                ('El servidor no confirmó la aceptación; revisa si llegó antes de reintentar.' if job.status=='UNCERTAIN' else 'Revisa la configuración de correo e inténtalo de nuevo.'))
        if diagnostic:
            detail+='\nFase: '+str(diagnostic.get('phase','—'))+' · Librería: '+str(diagnostic.get('exception','—'))
            if diagnostic.get('smtp_code') is not None:detail+=' · Código SMTP: '+str(diagnostic['smtp_code'])
            detail+='\nRespuesta: '+str(diagnostic.get('response','—'))
            if diagnostic.get('reference'):detail+='\nReferencia: '+diagnostic['reference']
        raise HTTPException(502,detail)
