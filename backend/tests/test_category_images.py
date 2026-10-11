import io
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import MaterialArea, MaterialAreaImage

bootstrap()

def test_upload_replacement_and_permissions():
    client = TestClient(app)
    with SessionLocal() as db:
        area = MaterialArea(code='TEST-IMAGE', name='Imagen de prueba')
        db.add(area)
        db.commit()
        area_id = area.id
    endpoint = f'/api/v1/store/category-visibility/{area_id}/image'
    client.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'})
    assert client.post(endpoint, files={'file':('fake.png',b'invalid','image/png')}).status_code == 422
    urls = []
    for color in ['blue','green']:
        buf = io.BytesIO()
        Image.new('RGB',(20,20),color).save(buf,format='PNG')
        response = client.post(endpoint, files={'file':('image.png',buf.getvalue(),'image/png')})
        assert response.status_code == 200
        urls.append(response.json()['image_url'])
        image_response = client.get(urls[-1])
        assert image_response.headers['content-type'] == 'image/webp'
        with Image.open(io.BytesIO(image_response.content)) as stored:
            assert stored.size == (20,20)
    assert urls[0] != urls[1]
    with SessionLocal() as db:
        assert db.get(MaterialAreaImage,area_id).filename == 'image.png'
        assert db.get(MaterialArea,area_id).name == 'Imagen de prueba'
    client.patch(f'/api/v1/store/category-visibility/{area_id}',json={'visible':False})
    assert client.get(urls[-1]).status_code == 200
    client.post('/api/v1/auth/login', json={'email':'compras001@cliente.test','password':'123456'})
    assert client.post(endpoint,files={'file':('fake.png',b'invalid','image/png')}).status_code == 403
    assert client.get(urls[-1]).status_code == 404
