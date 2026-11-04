from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.order_status_email import STATES, MESSAGES, render_status_email, example_email
from app import order_email_settings as mail
from app.bootstrap import main as bootstrap
bootstrap()
URL='https://extranet.bermudezulloa.es/seguimiento#token='+'a'*43


def payload(state='ENTREGADO_PARCIAL',**extra):
    return {'web_number':'WEB-2026-0000321','exit_number':'6008552','state':state,
        'expected_at':'2026-11-05T15:00:00Z',
        'pickup_summary':{'state':state,'total_materials':7,'delivered_materials':2,
            'delivered_percent':99,'legacy_delivery':False,'last_pickup_at':'2026-11-05T14:24:00Z'},**extra}


@pytest.mark.parametrize('state',list(STATES))
def test_each_state_has_concise_html_and_plain_message(state):
    result=example_email(state,'https://extranet.bermudezulloa.es/')
    assert STATES[state] in result['subject']
    assert MESSAGES[state] in result['text']
    assert len(MESSAGES[state].split())<35
    assert result['html'].startswith('<!doctype html>')
    assert 'EJEMPLO' in result['text'] and 'Abrir extranet' in result['text']
    assert '<script' not in result['html'] and '<img' not in result['html']
    assert 'No corresponde a un pedido real' in result['html']


def test_matches_tracking_progress_and_relevant_dates_without_private_data():
    result=render_status_email(payload(notes='PRIVATE_OPERATOR_NOTE',customer={'tax_id':'PRIVATE_TAX'},items=[{'description':'PRIVATE_DESCRIPTION','unit_price':99999}]),URL)
    assert result['progress']=={'percent':28,'completed':2,'total':7}
    assert '28%' in result['text'] and '2 de 7 materiales completos' in result['text']
    assert 'Última recogida: 05/11/2026, 15:24' in result['text']
    assert 'Fecha prevista' not in result['text']
    assert 'Ver seguimiento del pedido' in result['html'] and URL in result['text']
    assert 'EJEMPLO' not in result['text']
    for private in ['PRIVATE_OPERATOR_NOTE','PRIVATE_TAX','PRIVATE_DESCRIPTION','99999']:
        assert private not in result['text']+result['html']


def test_invoicing_never_means_physical_pickup_complete():
    result=render_status_email(payload(state='FACTURADO',pickup_summary={'state':'PENDIENTE_RECOGIDA_TOTAL','total_materials':7,'delivered_materials':2}),URL)
    assert result['state']=='PENDIENTE_RECOGIDA_TOTAL'
    assert result['progress']['percent']==28
    assert 'Pedido facturado.' in result['text'] and 'recoger todos los materiales pendientes' in result['text']
    standalone=render_status_email({'state':'FACTURADO','web_number':'WEB-1'},URL)
    assert standalone['progress'] is None and 'pendientes de recoger' in standalone['text']


def test_legacy_without_ledger_and_empty_lines_have_no_false_progress():
    for state in ['REVISAR_ENTREGA_HISTORICA','SIN_MATERIALES_ACTIVOS']:
        result=render_status_email(payload(state),URL)
        assert result['progress'] is None
        assert 'Avance' not in result['text'] and '0%' not in result['text']
    result=render_status_email({'state':'ATENDIDO','web_number':'WEB-1'},URL)
    assert result['state']=='PENDIENTE_RECOGIDA'
    assert 'todos los materiales' not in result['text']
    assert result['progress'] is None


def test_total_delivery_and_removed_order():
    result=render_status_email(payload('ENTREGADO_TOTAL',pickup_summary={'state':'ENTREGADO_TOTAL','total_materials':7,'delivered_materials':7,'completed_at':datetime(2026,11,5,14,24,tzinfo=timezone.utc)}),URL)
    assert result['progress']['percent']==100
    assert 'Recogida completada: 05/11/2026, 15:24' in result['text']
    assert 'Fecha prevista' not in result['text']
    result=render_status_email(payload(state='ELIMINADO_EN_EXIT',pickup_summary={'state':'EN_PREPARACION','total_materials':7,'delivered_materials':0}),URL)
    assert result['state']=='ELIMINADO_EN_EXIT' and result['progress'] is None
    assert 'no va a atenderse' in result['text']


def test_dynamic_html_is_escaped_and_subject_cannot_inject_headers():
    result=render_status_email(payload(web_number='<script>alert(1)</script>\nBcc: x',exit_number='<img src=x onerror=alert(1)>'),URL)
    assert '<script>' not in result['html'] and '<img' not in result['html']
    assert '&lt;script&gt;' in result['html']
    assert '\n' not in result['subject']
    for invalid in ['javascript:alert(1)','http://example.test','https://u:p@example.test','https://example.test/\nwrong']:
        with pytest.raises(ValueError):render_status_email(payload(),invalid)


def test_preview_permission_and_test_use_same_multipart_template(monkeypatch):
    path='/api/v1/store/order-email-settings'
    anonymous=TestClient(app);assert anonymous.get(path+'/preview').status_code==401
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert customer.get(path+'/preview').status_code==403
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    smtp=MagicMock();smtp.__enter__.return_value=smtp;smtp.send_message.return_value={}
    connect=MagicMock(return_value=smtp);monkeypatch.setattr(mail.smtplib,'SMTP',connect)
    assert client.put(path,json={'smtp_host':'smtp.example.test','password':'private-secret'}).status_code==200
    preview=client.get(path+'/preview?state=ENTREGADO_PARCIAL');assert preview.status_code==200
    assert 'no-store' in preview.headers['cache-control']
    assert preview.json()['progress']['percent']==28
    assert not connect.called,'Preview must never send an email'
    assert client.get(path+'/preview?state=INTERNAL').status_code==422
    assert client.post(path+'/test',json={'recipient':'receiver@example.test','preview_state':'INTERNAL'}).status_code==422
    assert client.post(path+'/test',json={'recipient':'receiver@example.test','preview_state':'ENTREGADO_PARCIAL'}).status_code==200
    message=smtp.send_message.call_args.args[0]
    assert message['Subject'].startswith('[PRUEBA]')
    assert message.get_body(preferencelist=('plain',)).get_content().strip()==preview.json()['text']
    assert message.get_body(preferencelist=('html',)).get_content().strip()==preview.json()['html']
    assert 'private-secret' not in str(message)
