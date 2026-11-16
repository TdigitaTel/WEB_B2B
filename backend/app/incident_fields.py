"""Validación de los datos configurados en una etapa, contra su versión guardada."""
from datetime import date
import re
from fastapi import HTTPException


def validate_fields(step,values):
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
        result.append({**field,'value':value})
    return result
