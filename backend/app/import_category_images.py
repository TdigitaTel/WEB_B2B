"""Initial category images: python -m app.import_category_images /tmp/images.zip."""
import hashlib
import io
import re
import sys
import unicodedata
import zipfile
from PIL import Image
from sqlalchemy import select
from .category_visibility import optimized_image
from .db import SessionLocal
from .models import MaterialArea, MaterialAreaImage


def slug(name):
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def import_images(db, path):
    areas = {slug(area.name): area for area in db.scalars(select(MaterialArea)).all()}
    added, preserved = 0, 0
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.lower().endswith('.png'):
                continue
            key = entry.filename.rsplit('/', 1)[-1][:-4]
            area = areas.get(key)
            if area is None:
                raise ValueError(f'Categoría no encontrada: {key}')
            if db.get(MaterialAreaImage, area.id) is not None:
                preserved += 1
                continue
            if entry.file_size > 10 * 1024 * 1024:
                raise ValueError(f'Imagen demasiado grande: {key}')
            content = archive.read(entry)
            with Image.open(io.BytesIO(content)) as image:
                if image.format != 'PNG' or max(image.size) > 4096:
                    raise ValueError(f'Imagen no admitida: {key}')
                image.verify()
            content = optimized_image(content)
            db.add(MaterialAreaImage(area_id=area.id, filename=key+'.png',
                       mime_type='image/webp', image_data=content,
                       sha256=hashlib.sha256(content).hexdigest()))
            db.flush()
            added += 1
    return {'cargadas': added, 'existentes_conservadas': preserved}


if __name__ == '__main__':
    with SessionLocal() as db:
        result = import_images(db, sys.argv[1])
        before = after = count = 0
        for row in db.scalars(select(MaterialAreaImage)).all():
            if row.mime_type == 'image/webp':
                continue
            before += len(row.image_data)
            row.image_data = optimized_image(row.image_data)
            after += len(row.image_data)
            row.mime_type = 'image/webp'
            row.sha256 = hashlib.sha256(row.image_data).hexdigest()
            count += 1
        db.commit()
        print(result, {'optimizadas': count, 'bytes_antes': before, 'bytes_despues': after})
