import io
from fastapi.testclient import TestClient
from PIL import Image
from app.bootstrap import main as bootstrap
from app.main import app

bootstrap()

def login(email):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client

def test_login_image_upload_public_read_and_restore():
    guest=TestClient(app)
    customer=login('compras001@cliente.test')
    operator=login('operador@bermudez.test')
    assert customer.delete('/api/v1/login-appearance').status_code==403
    assert guest.put('/api/v1/login-appearance',files={'file':('image.png',b'bad','image/png')}).status_code==401
    assert operator.put('/api/v1/login-appearance',files={'file':('image.svg',b'<svg></svg>','image/svg+xml')}).status_code==422
    data=io.BytesIO();Image.new('RGB',(600,400),'navy').save(data,'PNG')
    result=operator.put('/api/v1/login-appearance',files={'file':('image.png',data.getvalue(),'image/png')})
    assert result.status_code==200,result.text
    url=result.json()['image_url']
    assert guest.get('/api/v1/login-appearance').json()['image_url']==url
    response=guest.get(url)
    assert response.status_code==200 and response.headers['content-type']=='image/webp'
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size==(600,400) and image.format=='WEBP'
    assert operator.delete('/api/v1/login-appearance').json()=={'image_url':None}
    assert guest.get(url).status_code==404

def test_login_image_size_limit():
    operator=login('operador@bermudez.test')
    response=operator.put('/api/v1/login-appearance',files={'file':('big.png',b'0'*(8*1024*1024+1),'image/png')})
    assert response.status_code==413
