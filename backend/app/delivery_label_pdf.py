"""Thermal delivery labels. All text/barcodes remain vector; only thumbnails are raster."""
from io import BytesIO
import math
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode.code128 import Code128
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import reportlab

# Bundled, embedded fonts render consistently without depending on Windows fonts.
_font_dir = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('Label', str(_font_dir / 'Vera.ttf')))
pdfmetrics.registerFont(TTFont('Label-Bold', str(_font_dir / 'VeraBd.ttf')))

WIDTH, HEIGHT = 101.6*mm, 76.2*mm


def text(c, value, x, y, size=8, bold=False, width=93.6):
    font = 'Label-Bold' if bold else 'Label'
    value = str(value or '').replace('\n', ' ')
    while stringWidth(value, font, size) > width*mm and size > 6:
        size -= .25
    if stringWidth(value, font, size) > width*mm:
        while value and stringWidth(value+'…', font, size) > width*mm:
            value = value[:-1]
        value += '…'
    c.setFont(font, size)
    c.drawString(x*mm, y*mm, value)


def barcode(c, value, y, caption=None, height=7):
    value = str(value)
    if not value or any(ord(ch) < 32 or ord(ch) > 126 for ch in value):
        raise ValueError('El código de barras requiere caracteres ASCII imprimibles')
    # At least two 203-dpi dots per narrow bar, with explicit quiet zones.
    code = Code128(value, barWidth=72/203*3, barHeight=height*mm, quiet=True)
    if code.width > 93.6*mm:
        code = Code128(value, barWidth=72/203*2, barHeight=height*mm, quiet=True)
    if code.width > 93.6*mm:
        raise ValueError('Identificador demasiado largo para un código de barras legible en esta etiqueta')
    code.drawOn(c, (WIDTH-code.width)/2, y*mm)
    text(c, caption or value, 4, y-3, 7)


def date_text(value):
    if not value:
        return '—'
    return value.strftime('%d/%m/%Y') if hasattr(value, 'strftime') else str(value)[:10]


def references(note):
    document = f"{note['year']}/{note['series']}/{note['document_number']}"
    order = None
    if note.get('exit_order_number') and str(note['exit_order_number']) != '0':
        order = f"{note['exit_order_year']}/{note.get('exit_series') or ''}/{note['exit_order_number']}"
    return document, order


def codes(note):
    doc, order = references(note)
    return f"A{note['company_code']}/{doc}", f"P{note['company_code']}/{order}" if order else None


def detail_page(c, note, item, index, copies, thumbnail):
    doc, order = references(note)
    a_code, _ = codes(note)
    text(c, f"{note['customer_code']} · {note['customer_name']}", 4, 71.5, 9, True)
    dispatch = item.get('dispatch_delegation') or note.get('store_name') or note['store_code']
    text(c, f"DESPACHO: {dispatch}", 4, 66, 10, True)
    c.line(4*mm, 63*mm, 97.6*mm, 63*mm)
    text(c, item['sku'], 4, 57, 14, True, 68)
    words = str(item.get('description') or '').split()
    lines, line = [], ''
    for word in words:
        if stringWidth((line+' '+word).strip(), 'Label', 8) > 67*mm:
            lines.append(line); line = word
        else:
            line = (line+' '+word).strip()
    if line: lines.append(line)
    for n, line in enumerate(lines[:3]):
        text(c, line, 4, 52-n*4, 8, width=67)
    if thumbnail:
        try:
            image = ImageReader(BytesIO(thumbnail))
            c.drawImage(image, 74*mm, 41*mm, 23*mm, 20*mm, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            text(c, 'Sin miniatura', 74, 49, 6, width=23)
    else:
        text(c, 'Sin miniatura', 74, 49, 6, width=23)
    text(c, f"Cantidad: {item['quantity']:g} {item.get('unit') or 'UD'}", 4, 35, 11, True)
    text(c, f"Etiqueta {index}/{copies} · Fecha albarán {date_text(note.get('created_at'))}", 4, 30, 7)
    barcode(c, item['sku'], 20, item['sku'], height=6)
    barcode(c, a_code, 6, f"ALBARÁN {doc}", height=7)
    c.showPage()


def packing_page(c, note, items, page, pages):
    doc, order = references(note)
    a_code, p_code = codes(note)
    text(c, f"PACKING {page}/{pages} · Albarán {date_text(note.get('created_at'))}", 4, 72, 8, True)
    text(c, f"DESPACHO: {note.get('store_name') or note['store_code']}", 4, 67, 10, True)
    text(c, f"{note['customer_code']} · {note['customer_name']}", 4, 62, 8, True)
    text(c, note.get('customer_address'), 4, 58, 6.5)
    if p_code:
        text(c, f"Fecha pedido: {date_text(note.get('order_date'))}", 4, 54, 6.5, width=53)
        if note.get('customer_tax_id'):
            text(c, f"NIF: {note['customer_tax_id']}", 60, 54, 6.5, width=37)
        barcode(c, p_code, 44, f"PEDIDO {order}", height=7)
    else:
        text(c, 'Sin pedido vinculado', 4, 45, 8)
    barcode(c, a_code, 30, f"ALBARÁN {doc}", height=7)
    text(c, 'MATERIAL / DESCRIPCIÓN', 4, 23, 6.5, True)
    text(c, 'CANTIDAD', 80, 23, 6.5, True, 17)
    c.line(4*mm, 22*mm, 97.6*mm, 22*mm)
    for n, item in enumerate(items):
        y = 18-n*6
        text(c, f"{item['sku']} · {item.get('description') or ''}", 4, y, 7, width=73)
        text(c, f"{item['quantity']:g} {item.get('unit') or 'UD'}", 80, y, 8, True, 17)
        dispatch = item.get('dispatch_delegation')
        if dispatch and dispatch != note.get('store_name'):
            text(c, f"Salida: {dispatch}", 4, y-2.8, 6, width=73)
    c.showPage()


def generate_pdf(jobs, thumbnails=None):
    thumbnails = thumbnails or {}
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(WIDTH, HEIGHT), pageCompression=1)
    c.setTitle('Etiquetas de albaranes · 101,6 × 76,2 mm')
    for note, detail, packing, quantities in jobs:
        if detail:
            for item in note['items']:
                copies = quantities.get(item['line'], 1)
                for n in range(copies):
                    detail_page(c, note, item, n+1, copies, thumbnails.get(item['sku']))
        if packing:
            pages = max(1, math.ceil(len(note['items'])/3))
            for n in range(pages):
                packing_page(c, note, note['items'][n*3:(n+1)*3], n+1, pages)
    c.save()
    return output.getvalue()
