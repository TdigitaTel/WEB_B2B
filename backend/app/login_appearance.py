"""Imagen pública de acceso, administrada por los operadores."""
import io
import uuid
import warnings
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .db import get_db
from .models import LoginAppearance, User

router = APIRouter(prefix="/api/v1/login-appearance", tags=["appearance"])
LIMIT = 8 * 1024 * 1024

def config(row):
    return {"image_url": f"/api/v1/login-appearance/image?v={row.revision}" if row and row.image_data else None}

@router.get("")
def read(db: Session = Depends(get_db)):
    return config(db.get(LoginAppearance, 1))

@router.get("/image")
def image(db: Session = Depends(get_db)):
    row = db.get(LoginAppearance, 1)
    if not row or not row.image_data:
        raise HTTPException(404, "No hay imagen personalizada")
    return Response(row.image_data, media_type="image/webp", headers={"Cache-Control":"no-cache", "X-Content-Type-Options":"nosniff"})

@router.put("")
async def upload(file: UploadFile = File(...), user: User = Depends(require_roles("ADMIN", "OPERADOR_TIENDA")), db: Session = Depends(get_db)):
    data = await file.read(LIMIT + 1)
    await file.close()
    if len(data) > LIMIT:
        raise HTTPException(413, "La imagen debe ocupar como máximo 8 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Formato no admitido")
                if original.width * original.height > 20_000_000:
                    raise ValueError("La imagen supera 20 megapíxeles")
                picture = ImageOps.exif_transpose(original).convert("RGB")
                picture.thumbnail((2400, 2400))
                output = io.BytesIO()
                picture.save(output, "WEBP", quality=88)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "Selecciona una imagen JPG, PNG o WebP válida, de hasta 20 megapíxeles")
    row = db.get(LoginAppearance, 1)
    if row is None:
        row = LoginAppearance(id=1)
        db.add(row)
    row.image_data = output.getvalue()
    row.revision = str(uuid.uuid4())
    audit(db, user, "LOGIN_IMAGE_UPDATED", "LOGIN_APPEARANCE")
    db.commit()
    return config(row)

@router.delete("")
def restore(user: User = Depends(require_roles("ADMIN", "OPERADOR_TIENDA")), db: Session = Depends(get_db)):
    row = db.get(LoginAppearance, 1)
    if row:
        row.image_data = None
        row.revision = str(uuid.uuid4())
    audit(db, user, "LOGIN_IMAGE_RESTORED", "LOGIN_APPEARANCE")
    db.commit()
    return config(row)
