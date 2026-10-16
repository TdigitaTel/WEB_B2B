from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import User, Product
from app.main import app

bootstrap()


def test_preferences_persist_for_current_user_only():
    client=TestClient(app)
    assert client.patch('/api/v1/account/preferences',json={'show_delivery_note_images':True,'show_order_images':False}).status_code==401
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    first=client.get('/api/v1/account').json()['user']
    assert first['show_delivery_note_images'] is False and first['show_order_images'] is False
    response=client.patch('/api/v1/account/preferences',json={'show_delivery_note_images':True,'show_order_images':False})
    assert response.status_code==200,response.text
    assert client.get('/api/v1/account').json()['user']['show_delivery_note_images'] is True
    assert client.patch('/api/v1/account/preferences',json={'show_delivery_note_images':True,'show_order_images':True,'email':'changed@example.test'}).status_code==422
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        other=db.scalar(select(User).where(User.email=='compras002@cliente.test'))
        assert user.show_delivery_note_images and not user.show_order_images
        assert not other.show_delivery_note_images and not other.show_order_images
    login=client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert login.json()['user']['show_delivery_note_images'] is True
    assert client.patch('/api/v1/account/preferences',json={'show_delivery_note_images':False,'show_order_images':True}).status_code==200
    current=client.get('/api/v1/account').json()['user']
    assert not current['show_delivery_note_images'] and current['show_order_images']


def test_thumbnail_uses_existing_product_image(monkeypatch):
    from app import main as module
    from fastapi import Response
    client=TestClient(app)
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    with SessionLocal() as db:
        product=db.scalar(select(Product));sku=product.sku;pid=product.public_id
    seen=[]
    monkeypatch.setattr(module,'product_image',lambda product_id,user,db:(seen.append(product_id) or Response(content=b'image',media_type='image/png')))
    assert client.get(f'/api/v1/products/by-sku/{sku}/image').status_code==200
    assert seen==[pid]
    assert client.get('/api/v1/products/by-sku/UNKNOWN-IMAGE-TEST/image').status_code==404
