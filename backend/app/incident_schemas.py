from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from .order_email_settings import email_address

Mode=Literal['FORBIDDEN','OPTIONAL','REQUIRED']
Kind=Literal['SALE','PURCHASE','REPLENISHMENT','INVENTORY','TRANSFER']

class Destination(BaseModel):
    user_id:int=Field(gt=0)
    email:str
    @field_validator('email')
    @classmethod
    def address(cls,value):return email_address(value)

class Step(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    kind:Literal['WORK','APPROVE','EXECUTE','CONFIRM']='WORK'
    scope:Literal['GENERAL','DELEGATION','ORIGIN','DESTINATION']='DELEGATION'
    general:Destination|None=None
    delegations:dict[str,Destination]=Field(default_factory=dict,max_length=200)
    substitute:Destination|None=None
    hours:int=Field(48,ge=1,le=8760)
    files:Literal['INHERIT','FORBIDDEN','OPTIONAL','REQUIRED']='INHERIT'
    require_document:bool=False
    @field_validator('name')
    @classmethod
    def valid_name(cls,value):
        if not value.strip() or any(ord(c)<32 for c in value):raise ValueError('Indica un nombre de etapa válido')
        return value.strip()

class TypeConfiguration(BaseModel):
    code:str=Field(min_length=1,max_length=40,pattern=r'^[A-Z][A-Z0-9_]*$')
    name:str=Field(min_length=1,max_length=120)
    kind:Kind
    active:bool=False
    file_mode:Mode='OPTIONAL'
    max_files:int=Field(10,ge=1,le=20)
    max_file_mb:int=Field(4,ge=1,le=8)
    extensions:list[Literal['jpg','png','webp','pdf','xlsx']]=Field(default_factory=lambda:['jpg','png','webp','pdf','xlsx'],max_length=5)
    notify:bool=True
    reasons:list[str]=Field(default_factory=lambda:['Falta de material','Cantidad incorrecta','Material equivocado','Diferencia de stock','Otro'],min_length=1,max_length=30)
    steps:list[Step]=Field(min_length=1,max_length=15)
    @field_validator('name')
    @classmethod
    def valid_name(cls,value):
        if not value.strip() or any(ord(c)<32 for c in value):raise ValueError('Indica un nombre de tipo válido')
        return value.strip()
    @model_validator(mode='after')
    def valid_flow(self):
        if any(not reason.strip() or len(reason)>160 for reason in self.reasons):raise ValueError('Revisa los motivos de incidencia')
        self.reasons=list(dict.fromkeys(reason.strip() for reason in self.reasons))
        if self.file_mode!='FORBIDDEN' and not self.extensions:raise ValueError('Selecciona al menos un formato de archivo')
        if self.file_mode=='FORBIDDEN' and any(step.files in {'OPTIONAL','REQUIRED'} for step in self.steps):raise ValueError('Un tipo que no admite archivos no puede exigirlos en una etapa')
        required_files=(1 if self.file_mode=='REQUIRED' else 0)+sum(step.files=='REQUIRED' for step in self.steps)
        if required_files>self.max_files:raise ValueError('El máximo de archivos debe permitir uno por cada etapa obligatoria')
        if self.kind=='INVENTORY':
            approval=[i for i,step in enumerate(self.steps) if step.kind=='APPROVE']
            execution=[i for i,step in enumerate(self.steps) if step.kind=='EXECUTE']
            if not approval or not execution or min(execution)<=min(approval):raise ValueError('Inventario necesita autorización antes de ejecutar el ajuste')
        return self

class SaveType(BaseModel):
    revision:int=Field(0,ge=0)
    configuration:TypeConfiguration

class Line(BaseModel):
    sku:str=Field(min_length=1,max_length=100)
    description:str=Field(default='',max_length=300)
    unit:str=Field(default='',max_length=80)
    expected:float|None=Field(None,ge=0,le=1e9,allow_inf_nan=False)
    actual:float|None=Field(None,ge=0,le=1e9,allow_inf_nan=False)
    counted:float|None=Field(None,ge=0,le=1e9,allow_inf_nan=False)
    system_stock:float|None=Field(None,ge=-1e9,le=1e9,allow_inf_nan=False)
    manual_stock:bool=False
    manual_reason:str=Field(default='',max_length=500)
    location:str=Field(default='',max_length=120)
    counted_at:datetime|None=None
    @field_validator('counted_at')
    @classmethod
    def zoned_count(cls,value):
        if value and value.tzinfo is None:raise ValueError('La fecha del recuento debe incluir su zona horaria')
        return value

class CreateIncident(BaseModel):
    type_code:str=Field(max_length=40)
    delegation_id:str=Field(min_length=1,max_length=80)
    destination_id:str|None=Field(None,max_length=80)
    document:str=Field(default='',max_length=160)
    reason:str=Field(min_length=1,max_length=160)
    description:str=Field(min_length=1,max_length=4000)
    priority:Literal['NORMAL','URGENT']='NORMAL'
    needed_on:date|None=None
    lines:list[Line]=Field(min_length=1,max_length=100)
    @field_validator('reason','description')
    @classmethod
    def nonempty(cls,value):
        if not value.strip():raise ValueError('Completa el motivo y la descripción')
        return value.strip()

class Action(BaseModel):
    version:int=Field(ge=1)
    action:Literal['SUBMIT','ADVANCE','RETURN','REJECT','COMMENT','REASSIGN','RESEND_EMAIL']
    note:str=Field(default='',max_length=4000)
    document:str=Field(default='',max_length=160)
    verification_note:str=Field(default='',max_length=1000)
    verification_source:Literal['EXIT','MANUAL']='EXIT'
    user_id:int|None=None
    email:str=''

class EditIncident(CreateIncident):
    version:int=Field(ge=1)
