import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import delete,select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import HomeCarouselImage,HomeCarouselSettings,LoginAppearance,User,OperatorAccess

bootstrap()
pytestmark=pytest.mark.usefixtures('operator_with_almeiras_access')


def picture(color='blue'):
    output=io.BytesIO();Image.new('RGB',(48,24),color).save(output,'WEBP');return output.getvalue()


@pytest.fixture(autouse=True)
def clean_carousel():
    with SessionLocal() as db:
        db.execute(delete(HomeCarouselImage));db.execute(delete(HomeCarouselSettings))
        initial=db.get(LoginAppearance,1)
        if initial is None:initial=LoginAppearance(id=1);db.add(initial)
        initial.image_data=picture();initial.revision='login-preserved';db.commit()


def clients():
    operator=TestClient(app);customer=TestClient(app)
    assert operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    assert customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    return operator,customer


def add(client,config,replace_id=None):
    data={'revision':config['revision']}
    if replace_id:data['replace_id']=replace_id
    return client.post('/api/v1/home-carousel',data=data,files={'file':('slide.webp',picture('red'),'image/webp')})


def test_initial_image_copy_independent_and_authorization():
    operator,customer=clients();url='/api/v1/home-carousel'
    assert TestClient(app).get(url).status_code==401
    initial=customer.get(url).json();assert initial['using_default'] and len(initial['images'])==1
    assert initial['images'][0]['image_url'].startswith('/api/v1/login-appearance/image')
    assert add(customer,initial).status_code==403
    saved=add(operator,initial);assert saved.status_code==200,saved.text
    config=saved.json();assert len(config['images'])==2 and not config['using_default']
    assert customer.get(config['images'][0]['image_url']).content==picture()
    assert TestClient(app).get(config['images'][0]['image_url']).status_code==401
    with SessionLocal() as db:
        login=db.get(LoginAppearance,1);assert login.revision=='login-preserved' and login.image_data==picture()
        login.image_data=picture('green');db.commit()
    assert customer.get(config['images'][0]['image_url']).content==picture()


def test_order_replacement_revision_and_minimum():
    operator,_=clients();url='/api/v1/home-carousel';initial=operator.get(url).json()
    config=add(operator,initial).json()
    assert add(operator,initial).status_code==409
    ids=[row['id'] for row in config['images']]
    assert operator.patch(url,json={'revision':config['revision'],'image_ids':[ids[0],ids[0]]}).status_code==422
    reversed_result=operator.patch(url,json={'revision':config['revision'],'image_ids':ids[::-1]})
    assert reversed_result.status_code==200,reversed_result.text
    config=reversed_result.json();assert [row['id'] for row in config['images']]==ids[::-1]
    replaced=add(operator,config,ids[0]);assert replaced.status_code==200,replaced.text
    config=replaced.json();assert len(config['images'])==2
    assert add(operator,config,'default').status_code==404
    removed=operator.delete(f"{url}/images/{ids[0]}",params={'revision':config['revision']})
    assert removed.status_code==200,removed.text
    config=removed.json();assert len(config['images'])==1
    assert operator.delete(f"{url}/images/{ids[1]}",params={'revision':config['revision']}).status_code==422


def test_ten_image_limit_and_validation():
    operator,_=clients();url='/api/v1/home-carousel';config=operator.get(url).json()
    for _ in range(9):
        response=add(operator,config);assert response.status_code==200,response.text
        config=response.json()
    assert len(config['images'])==10
    assert add(operator,config).status_code==422
    assert len(operator.get(url).json()['images'])==10
    bad=operator.post(url,data={'revision':config['revision']},files={'file':('x.png',b'not-image','image/png')})
    assert bad.status_code==422
    assert operator.get(url).json()['revision']==config['revision']


def test_operator_needs_parameters_permission():
    operator,_=clients();config=operator.get('/api/v1/home-carousel').json()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        access=db.get(OperatorAccess,user.id);access.permissions={**access.permissions,'settings':False};db.commit()
    assert add(operator,config).status_code==403
