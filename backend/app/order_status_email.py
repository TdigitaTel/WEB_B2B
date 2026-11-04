"""Concise customer emails from the same allowlisted data as public tracking."""
from datetime import datetime
from html import escape
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .order_email_texts import STATES, MESSAGES, LABELS, ALIASES
from .order_email_content import EmailContent


def clean(value, limit=100):
    return ' '.join(str(value or '').split())[:limit]


def format_date(value):
    if not value:
        return None
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo('UTC'))
        return stamp.astimezone(ZoneInfo('Europe/Madrid')).strftime('%d/%m/%Y, %H:%M')
    except (ValueError, TypeError):
        return None


def render_status_email(payload, tracking_url, *, demo=False, content=None):
    """No DB reads, secrets or mutation: caller supplies an authorized tracking URL."""
    content = content if isinstance(content, EmailContent) else EmailContent.model_validate(content or {})
    parsed = urlsplit(tracking_url or "")
    if content.show_link and (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in (tracking_url or ''))):
        raise ValueError('El enlace del correo debe ser HTTPS y no contener credenciales')
    summary = payload.get('pickup_summary') or {}
    raw_state = payload.get('state', 'PENDIENTE')
    state = summary.get('state') or ALIASES.get(raw_state, raw_state)
    # A withdrawn order takes priority. Invoicing must not hide a pending pickup.
    if raw_state == 'ELIMINADO_EN_EXIT':
        state = raw_state
    if state not in LABELS:
        state = 'EN_GESTION'
    web = clean(payload.get('web_number')) or 'Tu pedido'
    store = clean(payload.get('exit_number'))
    label, message = LABELS[state], content.messages[state]
    if not content.show_store_number:
        store = ''
    progress = None
    total, done = summary.get('total_materials'), summary.get('delivered_materials')
    if (state not in {'ELIMINADO_EN_EXIT','REVISAR_ENTREGA_HISTORICA','SIN_MATERIALES_ACTIVOS'}
            and isinstance(total, int) and not isinstance(total, bool) and total > 0
            and isinstance(done, int) and not isinstance(done, bool) and 0 <= done <= total
            and not summary.get('legacy_delivery')):
        progress = {'percent': done*100//total, 'completed': done, 'total': total}
    date_label = 'Fecha prevista de entrega / recogida'
    date_value = payload.get('expected_at')
    if state == 'ENTREGADO_TOTAL':
        date_label, date_value = 'Recogida completada', summary.get('completed_at') or payload.get('delivered_at')
    elif state == 'ENTREGADO_PARCIAL':
        date_label, date_value = 'Última recogida', summary.get('last_pickup_at')
    elif state in {'ELIMINADO_EN_EXIT','REVISAR_ENTREGA_HISTORICA','SIN_MATERIALES_ACTIVOS','FACTURADO'}:
        date_value = None
    date_text = format_date(date_value) if content.show_dates else None
    if not content.show_progress:
        progress = None
    button = content.button_text or 'Ver seguimiento del pedido'
    lines = ['Bermúdez Ulloa', f'{web} · {label}']
    if demo:
        lines.insert(0, 'EJEMPLO · No corresponde a un pedido real')
    if store:
        lines.append(f'Pedido en tienda: {store}')
    lines.extend(['', content.greeting, message])
    progress_html = ''
    if progress:
        lines.append(f"Avance de recogida: {progress['percent']}% · {done} de {total} materiales completos")
        width = progress['percent']
        progress_html = f'''<p style="margin:20px 0 8px;font-size:16px;font-weight:bold">Avance de recogida: {width}%</p><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#e4edf1;border-radius:4px"><tr><td width="{max(width,1)}%" height="8" style="background:{'#237b55' if width else '#e4edf1'}"></td><td></td></tr></table><p style="margin:8px 0 0;color:#526b7a;font-size:14px">{done} de {total} materiales completos</p>'''
    if date_text:
        lines.append(f'{date_label}: {date_text}')
    billing = raw_state == 'FACTURADO' and state != 'FACTURADO'
    if billing:
        lines.append('Pedido facturado.')
    material_text, material_html = [], ''
    if content.show_materials:
        items = payload.get('items') or []
        for item in items[:50]:
            title = clean(item.get('description'), 500) or clean(item.get('sku')) or 'Material'
            detail = 'Eliminado · no se atenderá' if item.get('removed_in_exit') else ''
            if content.show_quantities:
                detail = ' · '.join(filter(None, [detail, f"Pedido: {clean(item.get('quantity'))} {clean(item.get('unit'))}"]))
            material_text.append(' · '.join(filter(None,[title, detail])))
        if len(items)>50:
            material_text.append(f'Se muestran 50 de {len(items)} materiales.')
        if material_text:
            lines.extend(['', 'Materiales', *material_text])
            material_html = '<h2 style="font-size:18px">Materiales</h2>' + ''.join('<p style="border-bottom:1px solid #d4e1e8;padding:10px 0">'+escape(line)+'</p>' for line in material_text)
    if content.show_conditions and content.conditions:
        lines.extend(['', 'Condiciones', content.conditions])
    if content.show_link:
        lines.extend(['', f'{button}:', tracking_url])
    if content.closing:
        lines.extend(['', content.closing])
    if demo and content.show_link:
        lines.append('Este enlace abre la extranet; no se ha creado un seguimiento real.')
    escaped_web, escaped_store = escape(web), escape(store)
    html = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:16px;background:#f1f5f7;color:#233b49;font-family:Arial,sans-serif"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center"><table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;background:#fff;border:1px solid #d4e1e8;border-radius:12px"><tr><td style="padding:22px 24px;background:#174c70;color:white;border-radius:12px 12px 0 0;font-size:22px;font-weight:bold">Bermúdez Ulloa</td></tr><tr><td style="padding:24px;overflow-wrap:anywhere">{('<p style="margin:0 0 18px;color:#805500;font-size:13px">EJEMPLO · No corresponde a un pedido real</p>' if demo else '')}<p style="margin:0;color:#526b7a;font-size:14px">{escaped_web}</p><h1 style="font-size:25px;line-height:1.3;color:#174c70;margin:10px 0 16px">{escape(label)}</h1>{(f'<p style="color:#526b7a;font-size:14px">Pedido en tienda: {escaped_store}</p>' if store else '')}<p style="font-size:16px;line-height:1.6;margin:0">{escape(content.greeting).replace(chr(10),'<br>')}</p><p style="font-size:16px;line-height:1.6">{escape(message).replace(chr(10),'<br>')}</p>{progress_html}{(f'<p style="margin:20px 0;font-size:15px;line-height:1.5"><b>{escape(date_label)}</b><br>{escape(date_text)}</p>' if date_text else '')}{('<p style="color:#526b7a;font-size:14px">Pedido facturado.</p>' if billing else '')}{material_html}{('<h2 style="font-size:18px">Condiciones</h2><p style="line-height:1.6">'+escape(content.conditions).replace(chr(10),'<br>')+'</p>' if content.show_conditions and content.conditions else '')}{('<p style="margin-top:24px"><a href="'+escape(tracking_url,quote=True)+'" style="display:inline-block;padding:15px 20px;background:#1c608c;border-radius:8px;color:white;text-decoration:none;font-weight:bold">'+escape(button)+'</a></p>' if content.show_link else '')}<p style="font-size:14px;line-height:1.6;color:#607783">{escape(content.closing).replace(chr(10),'<br>')}</p>{('<p style="font-size:12px;color:#607783">Este enlace abre la extranet; no se ha creado un seguimiento real.</p>' if demo and content.show_link else '')}</td></tr></table></td></tr></table></body></html>'''
    return {'subject': ' · '.join(filter(None,[content.subject_prefix,web,label])), 'text': '\n'.join(lines), 'html': html, 'state': state, 'progress': progress}


def example_email(state, portal_url, *, content=None):
    if state not in LABELS:
        raise ValueError('Estado no disponible')
    counts = {'PENDIENTE_RECOGIDA_PARCIAL': (0,3), 'PENDIENTE_RECOGIDA_TOTAL': (0,7),
              'ENTREGADO_PARCIAL': (2,0), 'ENTREGADO_TOTAL': (7,0)}
    done, ready = counts.get(state, (0,0))
    summary = None if state in {'PENDIENTE','FACTURADO','ELIMINADO_EN_EXIT'} else {
        'state': state, 'total_materials':7, 'delivered_materials':done, 'ready_materials':ready,
        'legacy_delivery':False, 'last_pickup_at':'2026-11-05T14:24:00Z',
        'completed_at':'2026-11-05T14:24:00Z' if state=='ENTREGADO_TOTAL' else None}
    examples = ['Depósito de inercia inox 100 litros', 'Vaso de expansión 12 litros',
                'Vaso de expansión calefacción 18 litros', 'Filtro desfangador',
                'Soporte de vaso de expansión', 'Racor de latón', 'Manguito inoxidable']
    items = [{'sku':str(23000+i),'description':description,'quantity':1,'unit':'UD'}
             for i, description in enumerate(examples)]
    items.append({'description':'Material eliminado de ejemplo','quantity':1,'unit':'UD','removed_in_exit':True})
    return render_status_email({'web_number':'WEB-EJEMPLO','exit_number':'6000000','state':state,
        'expected_at':'2026-11-05T15:00:00Z','pickup_summary':summary,'items':items},
        portal_url, demo=True, content=content)
