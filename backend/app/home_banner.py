"""Diapositivas de inicio: metadatos ligeros e imágenes servidas por separado."""
import io
import uuid
import warnings
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only
from .auth import audit, require_roles
from .db import get_db
from .models import HomeBannerSettings as Settings, HomeBannerSlide as Slide, User

router=APIRouter(tags=['home-banner'])
operator=require_roles('ADMIN','OPERADOR_TIENDA')
LIMIT=8*1024*1024
DEFAULT={'id':'original','alt':'Todo lo que necesitas. Listo para tu próxima obra.','enabled':True,'image_url':None}


def config(db,public=False):
    settings=db.get(Settings,1)
    # Never load image bytes into the configuration response.
    query=select(Slide.id,Slide.alt,Slide.enabled,Slide.image_data.is_not(None).label('has_image')).order_by(Slide.position,Slide.id)
    if public:query=query.where(Slide.enabled.is_(True))
    slides=[{'id':row.id,'alt':row.alt,'enabled':row.enabled,'image_url':f'/api/v1/home-banner/images/{row.id}' if row.has_image else None} for row in db.execute(query)]
    if not settings or (public and not slides):slides=[dict(DEFAULT)]
    return {'interval_seconds':settings.interval_seconds if settings else 7,'revision':settings.revision if settings else 'initial','slides':slides}


def lock_settings(db):
    # Serialize list edits/uploads; a stale editor receives 409 rather than losing changes.
    # Lock the existing singleton user-independent settings row after initialization.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    created=db.execute(insert(Settings).values(id=1,interval_seconds=7,revision=str(uuid.uuid4())).on_conflict_do_nothing(index_elements=['id']).returning(Settings.id)).scalar_one_or_none()
    row=db.scalar(select(Settings).where(Settings.id==1).with_for_update())
    if created:db.add(Slide(id='original',position=0,enabled=True,alt=DEFAULT['alt']))
    db.flush()
    return row, bool(created)


@router.get('/api/v1/home-banner')
def read(response:Response,db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    return config(db,public=True)


@router.get('/api/v1/store/home-banner')
def manage(response:Response,user:User=Depends(operator),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    return config(db)


@router.get('/api/v1/home-banner/images/{slide_id}')
def image(slide_id:str,db:Session=Depends(get_db)):
    data=db.scalar(select(Slide.image_data).where(Slide.id==slide_id,Slide.enabled.is_(True)))
    if not data:raise HTTPException(404,'La imagen no está disponible')
    return Response(data,media_type='image/webp',headers={'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'})


@router.get('/api/v1/store/home-banner/images/{slide_id}')
def preview_image(slide_id:str,user:User=Depends(operator),db:Session=Depends(get_db)):
    data=db.scalar(select(Slide.image_data).where(Slide.id==slide_id))
    if not data:raise HTTPException(404,'La imagen no está disponible')
    return Response(data,media_type='image/webp',headers={'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'})


@router.post('/api/v1/store/home-banner/images',status_code=201)
async def upload(file:UploadFile=File(...),user:User=Depends(operator),db:Session=Depends(get_db)):
    data=await file.read(LIMIT+1)
    await file.close()
    if len(data)>LIMIT:raise HTTPException(413,'La imagen debe ocupar como máximo 8 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {'JPEG','PNG','WEBP'} or original.width*original.height>20_000_000:raise ValueError()
                picture=ImageOps.exif_transpose(original).convert('RGB')
                picture.thumbnail((2400,2400))
                output=io.BytesIO();picture.save(output,'WEBP',quality=88)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Selecciona una imagen JPG, PNG o WebP válida, de hasta 20 megapíxeles')
    settings,_=lock_settings(db)
    count=db.scalar(select(Slide.position).order_by(Slide.position.desc()).limit(1))
    db.add(Slide(position=(count if count is not None else -1)+1,enabled=True,image_data=output.getvalue(),alt='Información de Bermúdez Ulloa'))
    settings.revision=str(uuid.uuid4())
    audit(db,user,'HOME_BANNER_IMAGE_ADDED','HOME_BANNER')
    db.commit()
    return config(db)


class SlideInput(BaseModel):
    id:str=Field(min_length=1,max_length=36)
    alt:str=Field(max_length=200)
    enabled:bool


class ConfigInput(BaseModel):
    revision:str=Field(min_length=1,max_length=36)
    interval_seconds:int=Field(7,ge=3,le=120)
    slides:list[SlideInput]


@router.put('/api/v1/store/home-banner')
def update(body:ConfigInput,user:User=Depends(operator),db:Session=Depends(get_db)):
    settings,created=lock_settings(db)
    if body.revision!=('initial' if created else settings.revision):raise HTTPException(409,'Otro operador ha cambiado el banner. Recarga la configuración antes de guardar.')
    rows={row.id:row for row in db.scalars(select(Slide).options(load_only(Slide.id,Slide.position,Slide.enabled,Slide.alt)))}
    ids=[slide.id for slide in body.slides]
    if len(ids)!=len(set(ids)) or set(ids)!=set(rows):raise HTTPException(422,'La lista de imágenes no coincide. Recarga la configuración.')
    for position,slide in enumerate(body.slides):
        rows[slide.id].position=position;rows[slide.id].enabled=slide.enabled;rows[slide.id].alt=slide.alt.strip() or 'Información de Bermúdez Ulloa'
    settings.interval_seconds=body.interval_seconds;settings.revision=str(uuid.uuid4())
    audit(db,user,'HOME_BANNER_UPDATED','HOME_BANNER');db.commit()
    return config(db)


@router.delete('/api/v1/store/home-banner/images/{slide_id}')
def delete(slide_id:str,revision:str=Query(...,min_length=1,max_length=36),user:User=Depends(operator),db:Session=Depends(get_db)):
    settings,created=lock_settings(db)
    if revision!=('initial' if created else settings.revision):raise HTTPException(409,'Otro operador ha cambiado el banner. Recarga la configuración antes de eliminar.')
    slide=db.scalar(select(Slide).where(Slide.id==slide_id).options(load_only(Slide.id)))
    if not slide:raise HTTPException(404,'La imagen ya no existe')
    db.delete(slide);settings.revision=str(uuid.uuid4())
    audit(db,user,'HOME_BANNER_IMAGE_DELETED','HOME_BANNER');db.commit()
    return config(db)
