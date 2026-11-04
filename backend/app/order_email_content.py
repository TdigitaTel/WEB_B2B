"""Validated, persisted editorial choices for order mail."""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .order_email_texts import MESSAGES


class EmailContent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject_prefix: str = Field(default='Pedido', max_length=100)
    greeting: str = Field(default='Hola,', max_length=500)
    messages: dict[str, str] = Field(default_factory=lambda: dict(MESSAGES))
    closing: str = Field(default='Gracias por confiar en Bermúdez Ulloa.', max_length=2000)
    conditions: str = Field(default='', max_length=4000)
    show_progress: bool = True
    show_dates: bool = True
    show_store_number: bool = True
    show_materials: bool = False
    show_quantities: bool = True
    show_conditions: bool = False
    show_link: bool = True
    button_text: str = Field(default='Ver seguimiento del pedido', max_length=100)

    @field_validator('subject_prefix','button_text')
    @classmethod
    def single_line(cls, value):
        if any(ord(char)<32 or ord(char)==127 for char in value):
            raise ValueError('Escribe este texto en una sola línea')
        return value.strip()

    @field_validator('messages')
    @classmethod
    def known_messages(cls, value):
        if any(key not in MESSAGES or len(text)>3000 for key,text in value.items()):
            raise ValueError('Selecciona un estado válido y un mensaje de hasta 3000 caracteres')
        # Missing keys retain the editable starter; an explicit empty string removes it.
        return {**MESSAGES,**value}

    @model_validator(mode='after')
    def link_has_caption(self):
        if self.show_link and not self.button_text:
            raise ValueError('Escribe el texto del botón o desactiva el enlace directo')
        return self
