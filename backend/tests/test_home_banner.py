import io
import pytest
from PIL import Image
from sqlalchemy import delete
from fastapi.testclient import TestClient
from app.bootstrap import main as bootstrap
from app.main import app
from app.db import SessionLocal
from app.models import HomeBannerSettings,HomeBannerSlide

bootstrap()
BASE='/api/v1/store/home-banner'
PUBLIC='/api/v1/home-banner'

@pytest.fixture(autouse=True)
def clear_banner():
    with SessionLocal() as db:
        db.execute(delete(HomeBannerSlide));db.execute(delete(HomeBannerSettings));db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(HomeBannerSlide));db.execute(delete(HomeBannerSettings));db.commit()


def login(email='operador@bermudez.test'):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


def picture():
    data=io.BytesIO();Image.new('RGB',(1600,320),'navy').save(data,'PNG');return data.getvalue()


def test_banner_permissions_order_visibility_revision_and_separate_images():
    guest=TestClient(app);customer=login('compras001@cliente.test');operator=login()
    initial=guest.get(PUBLIC)
    assert initial.json()['slides'][0]['id']=='original' and 'no-store' in initial.headers['cache-control']
    assert initial.json()['interval_seconds']==5
    assert guest.get(BASE).status_code==401
    assert customer.get(BASE).status_code==403
    assert customer.post(BASE+'/images',files={'file':('a.png',picture(),'image/png')}).status_code==403
    # Multiple uploads append without a one-image replacement or a fixed gallery cap.
    for _ in range(10):
        response=operator.post(BASE+'/images',files={'file':('a.png',picture(),'image/png')})
        assert response.status_code==201,response.text
    saved=response.json();assert len(saved['slides'])==11
    assert saved['interval_seconds']==5
    assert all('image_data' not in row for row in saved['slides'])
    image_url=saved['slides'][-1]['image_url']
    image=guest.get(image_url)
    assert image.status_code==200 and image.headers['content-type']=='image/webp'
    with Image.open(io.BytesIO(image.content)) as decoded:assert decoded.size==(1600,320)
    reordered=list(reversed(saved['slides']))
    reordered[0]['alt']='Promoción de invierno';reordered[1]['enabled']=False
    body={**saved,'slides':reordered,'interval_seconds':12}
    updated=operator.put(BASE,json=body)
    assert updated.status_code==200,updated.text
    current=guest.get(PUBLIC).json()
    assert current['interval_seconds']==12 and current['slides'][0]['alt']=='Promoción de invierno'
    assert len(current['slides'])==10
    assert guest.get(reordered[1]['image_url']).status_code==404
    preview=reordered[1]['image_url'].replace('/api/v1/home-banner/','/api/v1/store/home-banner/')
    assert operator.get(preview).status_code==200 and customer.get(preview).status_code==403
    assert operator.put(BASE,json=body).status_code==409
    assert operator.delete(BASE+'/images/'+reordered[0]['id'],params={'revision':saved['revision']}).status_code==409
    result=operator.delete(BASE+'/images/'+reordered[0]['id'],params={'revision':updated.json()['revision']})
    assert result.status_code==200 and len(result.json()['slides'])==10
    assert guest.get(image_url).status_code==404
    disabled=result.json()
    for slide in disabled['slides']:slide['enabled']=False
    assert operator.put(BASE,json=disabled).status_code==200
    assert guest.get(PUBLIC).json()['slides'][0]['id']=='original'


def test_banner_rejects_invalid_images_and_invalid_list_edits():
    operator=login()
    assert operator.post(BASE+'/images',files={'file':('a.svg',b'<svg/>','image/svg+xml')}).status_code==422
    assert operator.post(BASE+'/images',files={'file':('large.png',b'0'*(8*1024*1024+1),'image/png')}).status_code==413
    saved=operator.get(BASE).json()
    assert operator.put(BASE,json={**saved,'interval_seconds':2}).status_code==422
    assert operator.put(BASE,json={**saved,'slides':saved['slides']*2}).status_code==422
    assert operator.put(BASE,json={**saved,'slides':[]}).status_code==422
    assert operator.put(BASE,json=saved).status_code==200
