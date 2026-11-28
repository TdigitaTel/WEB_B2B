"""Operator-only delivery-note listing and label printing, scoped before reading EXIT."""
import logging
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from .auth import require_roles, audit
from .db import get_db
from .models import User, Product, LabelPrinterPreference
from .operator_permissions import delegation_scope
from .delegations import fetch_delegations
from .erp_db import fetch_customer_delivery_notes, fetch_product_image
from .config import settings
from .delivery_label_pdf import generate_pdf

router = APIRouter(prefix='/api/v1/store/delivery-labels', tags=['Albaranes y etiquetas'])
operator = require_roles('ADMIN', 'OPERADOR_TIENDA')
logger = logging.getLogger(__name__)


class PrinterIn(BaseModel):
    printer_name: str = Field('', max_length=240)
    dpi: Literal[203, 300, 600] = 203


class DocumentIn(BaseModel):
    company: int = Field(gt=0)
    year: int = Field(ge=1900, le=9999)
    series: str = Field('', max_length=30)
    number: int = Field(gt=0)
    detail: bool = True
    packing: bool = True
    quantities: dict[int, int] = Field(default_factory=dict, max_length=500)

    @model_validator(mode='after')
    def validate_job(self):
        if not (self.detail or self.packing):
            raise ValueError('Selecciona detalle, packing o ambos')
        if any(k < 0 or v < 0 or v > 100 for k, v in self.quantities.items()):
            raise ValueError('El número de etiquetas por línea debe estar entre 0 y 100')
        return self


class PrintIn(BaseModel):
    documents: list[DocumentIn] = Field(min_length=1, max_length=20)


def scoped_delegations(user, db):
    allowed = delegation_scope(user, db)
    allowed = None if allowed is None else {(int(c), d) for c, d in allowed}
    return [d for d in fetch_delegations() if allowed is None or (d.company, d.code) in allowed]


def preferences(row):
    return {'printer_name': row.printer_name if row else '', 'dpi': row.dpi if row else 203,
            'width_mm': 101.6, 'height_mm': 76.2}


@router.get('/preferences')
def get_preferences(user: User = Depends(operator), db=Depends(get_db)):
    return preferences(db.get(LabelPrinterPreference, user.id))


@router.put('/preferences')
def save_preferences(data: PrinterIn, user: User = Depends(operator), db=Depends(get_db)):
    row = db.get(LabelPrinterPreference, user.id)
    if row is None:
        row = LabelPrinterPreference(user_id=user.id); db.add(row)
    row.printer_name = data.printer_name.strip(); row.dpi = data.dpi
    db.commit()
    return preferences(row)


@router.get('')
def listing(document_number: str = Query('', max_length=100), date_from: date | None = None,
            date_to: date | None = None, delegation: str = Query('', max_length=80),
            page: int = Query(1, ge=1, le=10000), user: User = Depends(operator), db=Depends(get_db)):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'La fecha desde no puede ser posterior a hasta')
    try:
        stores = scoped_delegations(user, db)
        keys = [(d.company, d.code) for d in stores if not delegation or d.id == delegation]
        if delegation and not keys:
            raise HTTPException(403, 'Delegación no autorizada')
        rows = fetch_customer_delivery_notes(None, 26, document_number, date_from, date_to,
                                             delegation_keys=keys, offset=(page-1)*25)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Error consultando albaranes para etiquetas')
        raise HTTPException(503, 'No se pudieron consultar los albaranes en EXIT') from exc
    # This screen and labels never expose prices.
    clean = []
    for row in rows[:25]:
        clean.append({k: v for k, v in row.items() if k not in {'subtotal', 'tax_total', 'total', 'items'}} | {
            'items': [{k: v for k, v in item.items() if k in {'line', 'sku', 'description', 'quantity', 'unit', 'warehouse', 'dispatch_delegation'}} for item in row['items']]})
    return {'items': clean, 'page': page, 'has_more': len(rows)>25,
            'delegations': [{'id': d.id, 'name': d.name, 'company': d.company, 'code': d.code} for d in stores]}


@router.post('/pdf')
def print_labels(data: PrintIn, user: User = Depends(operator), db=Depends(get_db)):
    try:
        stores = scoped_delegations(user, db)
        keys = [(d.company, d.code) for d in stores]
        jobs, total = [], 0
        identities = set()
        for job in data.documents:
            identity = (job.company, job.year, job.series.strip(), job.number)
            if identity in identities:
                raise HTTPException(422, 'Albarán repetido en la selección')
            identities.add(identity)
            rows = fetch_customer_delivery_notes(None, 1, delegation_keys=keys, document_key=identity)
            if not rows:
                raise HTTPException(404, 'Albarán no encontrado o fuera de tus delegaciones autorizadas')
            note = rows[0]
            if set(job.quantities)-{item['line'] for item in note['items']}:
                raise HTTPException(409, 'El detalle del albarán ha cambiado; actualiza la lista')
            total += sum(job.quantities.get(item['line'], 1) for item in note['items']) if job.detail else 0
            total += max(1, (len(note['items'])+2)//3) if job.packing else 0
            if total > 500:
                raise HTTPException(422, 'Selecciona como máximo 500 etiquetas por impresión')
            jobs.append((note, job.detail, job.packing, job.quantities))
        if not total:
            raise HTTPException(422, 'Selecciona al menos una etiqueta')
        thumbnails = {}
        for note, detail, _, quantities in jobs:
            if not detail: continue
            for item in note['items']:
                sku = item['sku']
                if sku in thumbnails or not quantities.get(item['line'], 1): continue
                product = db.scalar(select(Product).where(Product.sku == sku))
                image = product.image_data if product and settings.product_image_source != 'sqlserver' else None
                if not image and settings.product_image_source != 'postgres':
                    try:
                        image = fetch_product_image(sku)
                    except Exception:
                        logger.warning('Miniatura no disponible para etiqueta %s', sku)
                thumbnails[sku] = image
        pdf = generate_pdf(jobs, thumbnails)
        audit(db, user, 'DELIVERY_LABELS_GENERATED', 'DELIVERY_NOTES', None, {'documents': [list(i) for i in sorted(identities)], 'labels': total})
        db.commit()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception('Error generando etiquetas de albaranes')
        raise HTTPException(503, 'No se pudieron generar las etiquetas. No se ha enviado nada a imprimir.') from exc
    return Response(pdf, media_type='application/pdf', headers={'Content-Disposition': 'inline; filename="etiquetas-albaranes.pdf"', 'Cache-Control': 'no-store', 'X-Label-Count': str(total)})
