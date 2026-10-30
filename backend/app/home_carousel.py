"""Promotional carousel, independent from the sign-in artwork."""
import io
import uuid
import warnings
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .auth import current_user, require_roles, audit
from .db import get_db
from .models import HomeCarouselSettings, HomeCarouselImage, LoginAppearance, User

router=APIRouter(prefix='/api/v1/home-carousel',tags=['appearance'])


def rows(db):
    return list(db.scalars(select(HomeCarouselImage).order_by(HomeCarouselImage.position,HomeCarouselImage.id)))


def config(db):
    settings=db.get(HomeCarouselSettings,1)
    images=rows(db)
    if images:
        items=[{'id':row.id,'image_url':f'/api/v1/home-carousel/images/{row.id}?v={row.revision}'} for row in images]
    else:
        initial=db.get(LoginAppearance,1)
        items=[{'id':'default','image_url':f'/api/v1/login-appearance/image?v={initial.revision}' if initial and initial.image_data else '/bermudez-ulloa-logo.jpg'}]
    return {'revision':settings.revision if settings else 'initial','images':items,'interval_seconds':5,'using_default':not bool(images)}


def lock(db,revision):
    if db.bind.dialect.name=='postgresql':
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('home-carousel',0))"))
    settings=db.get(HomeCarouselSettings,1)
    if revision!=(settings.revision if settings else 'initial'):
        raise HTTPException(409,'La lista ha cambiado. Actualiza antes de guardar.')
    if settings is None:
        settings=HomeCarouselSettings(id=1,revision='initial');db.add(settings)
    return settings


def materialize_default(db):
    initial=db.get(LoginAppearance,1)
    if not rows(db) and initial and initial.image_data:
        row=HomeCarouselImage(id=str(uuid.uuid4()),position=0,image_data=initial.image_data,revision=str(uuid.uuid4()))
        db.add(row);db.flush();return row
    return None


def finish(db,settings,user,action):
    settings.revision=str(uuid.uuid4())
    audit(db,user,action,'HOME_CAROUSEL')
    db.commit();return config(db)


@router.get('')
def read(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return config(db)


@router.get('/images/{image_id}')
def image(image_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.get(HomeCarouselImage,image_id)
    if row is None:raise HTTPException(404,'Imagen no encontrada')
    return Response(row.image_data,media_type='image/webp',headers={'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'})


@router.post('')
async def upload(file:UploadFile=File(...),revision:str=Form(...),replace_id:str|None=Form(None),
                 user:User=Depends(require_roles('ADMIN','OPERADOR_TIENDA')),db:Session=Depends(get_db)):
    data=await file.read(8*1024*1024+1);await file.close()
    if len(data)>8*1024*1024:raise HTTPException(413,'La imagen debe ocupar como máximo 8 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {'JPEG','PNG','WEBP'} or original.width*original.height>20_000_000:raise ValueError()
                picture=ImageOps.exif_transpose(original).convert('RGB');picture.thumbnail((2400,2400))
                output=io.BytesIO();picture.save(output,'WEBP',quality=88)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Selecciona una imagen JPG, PNG o WebP válida, de hasta 20 megapíxeles')
    settings=lock(db,revision)
    was_default = not bool(rows(db))
    if replace_id == 'default' and not was_default:
        raise HTTPException(404, 'Imagen inicial no disponible; actualiza la lista')
    initial=materialize_default(db)
    if replace_id:
        row=initial if replace_id=='default' else db.get(HomeCarouselImage,replace_id)
        if replace_id=='default' and row is None:
            row=HomeCarouselImage(id=str(uuid.uuid4()),position=0);db.add(row)
        if row is None:raise HTTPException(404,'Imagen no encontrada')
    else:
        existing=rows(db)
        if len(existing)>=10:raise HTTPException(422,'El carrusel admite como máximo 10 imágenes')
        row=HomeCarouselImage(id=str(uuid.uuid4()),position=len(existing));db.add(row)
    row.image_data=output.getvalue();row.revision=str(uuid.uuid4())
    return finish(db,settings,user,'HOME_CAROUSEL_IMAGE_SAVED')


class Reorder(BaseModel):
    revision:str
    image_ids:list[str]


@router.patch('')
def reorder(data:Reorder,user:User=Depends(require_roles('ADMIN','OPERADOR_TIENDA')),db:Session=Depends(get_db)):
    settings=lock(db,data.revision);existing=rows(db)
    if not 1<=len(data.image_ids)<=10 or len(set(data.image_ids))!=len(data.image_ids) or set(data.image_ids)!={row.id for row in existing}:
        raise HTTPException(422,'Incluye todas las imágenes una sola vez al ordenar')
    by_id={row.id:row for row in existing}
    for position,image_id in enumerate(data.image_ids):by_id[image_id].position=position
    return finish(db,settings,user,'HOME_CAROUSEL_REORDERED')


@router.delete('/images/{image_id}')
def remove(image_id:str,revision:str,user:User=Depends(require_roles('ADMIN','OPERADOR_TIENDA')),db:Session=Depends(get_db)):
    settings=lock(db,revision);existing=rows(db)
    if len(existing)<=1:raise HTTPException(422,'Debe quedar al menos una imagen')
    row=db.get(HomeCarouselImage,image_id)
    if row is None:raise HTTPException(404,'Imagen no encontrada')
    db.delete(row)
    for position,item in enumerate(item for item in existing if item.id!=image_id):item.position=position
    return finish(db,settings,user,'HOME_CAROUSEL_IMAGE_REMOVED')
