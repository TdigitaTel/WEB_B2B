"""Validación de los datos configurados en una etapa, contra su versión guardada."""
from datetime import date
import re
from fastapi import HTTPException


def validate_fields(step,values,lookup=None):
    definitions=step.get('fields',[])
    if set(values)-{field['key'] for field in definitions}:
        raise HTTPException(422,'Hay datos que no están configurados en esta etapa')
    result=[]
    for field in definitions:
        value=values.get(field['key'],'').strip()
        label=field['label']
        if not value:
            if field.get('required'):raise HTTPException(422,f'Completa el campo obligatorio «{label}»')
            continue
        if len(value)>1000:raise HTTPException(422,f'«{label}» supera los 1000 caracteres')
        if field['type']=='NUMBER' and not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',value):
            raise HTTPException(422,f'«{label}» debe ser un número válido')
        if field['type']=='DATE':
            try:
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError()
                date.fromisoformat(value)
            except ValueError:raise HTTPException(422,f'«{label}» debe ser una fecha válida')
        if field.get('validate_code'):
            if lookup is None or value not in lookup:raise HTTPException(422,f'«{label}»: código de material no válido en EXIT')
        result.append({**field,'value':value})
    return result


def validate_data(definitions, values, rows, material_reader):
    """Validate ordered header and repeated fields against the frozen workflow."""
    header=[field for field in definitions if not field.get('repeat')]
    repeated=[field for field in definitions if field.get('repeat')]
    if rows and not repeated:raise HTTPException(422,'Este formulario no tiene datos por línea')
    if not rows and any(field.get('required') for field in repeated):raise HTTPException(422,'Añade al menos una línea y completa sus campos obligatorios')
    codes={str(data.get(field['key'],'')).strip() for fields,data in [(header,values),*[(repeated,row) for row in rows]] for field in fields if field.get('validate_code') and str(data.get(field['key'],'')).strip()}
    try:catalog=material_reader(sorted(codes)) if codes else {}
    except Exception as exc:raise HTTPException(503,'No se pudo validar el código en EXIT. Reintenta antes de guardar') from exc
    result=validate_fields({'fields':header},values,catalog)
    for index,row in enumerate(rows):
        try:items=validate_fields({'fields':repeated},row,catalog)
        except HTTPException as exc:raise HTTPException(exc.status_code,f'Línea {index+1}: {exc.detail}') from exc
        present={item['key']:item for item in items}
        # Retain empty optional cells too, so line order and draft rows round-trip exactly.
        result.extend({**present.get(field['key'],{**field,'value':''}),'row':index+1} for field in repeated)
    return result


def input_values(fields):
    values={};rows=[]
    for field in fields:
        if 'row' in field:
            while len(rows)<field['row']:rows.append({})
            rows[field['row']-1][field['key']]=field['value']
        else:values[field['key']]=field['value']
    return {'fields':values,'field_rows':rows}
