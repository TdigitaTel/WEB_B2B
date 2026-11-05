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


def test_operator_order_photos_persist_without_changing_customer_preferences():
    client=TestClient(app)
    logged=client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    original=logged.json()['user']
    previous={key:original[key] for key in ['show_order_images','show_delivery_note_images']}
    with SessionLocal() as db:
        customer=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        customer_before=(customer.show_order_images,customer.show_delivery_note_images)
    try:
        body={**previous,'show_order_images':True}
        assert client.patch('/api/v1/account/preferences',json=body).status_code==200
        again=client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).json()['user']
        assert again['show_order_images'] is True
        assert again['show_delivery_note_images']==previous['show_delivery_note_images']
        with SessionLocal() as db:
            customer=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
            assert (customer.show_order_images,customer.show_delivery_note_images)==customer_before
    finally:
        client.patch('/api/v1/account/preferences',json=previous)


def test_operator_can_read_order_photos_only_with_orders_permission(monkeypatch):
    from app.models import OperatorAccess
    from app.config import settings
    client=TestClient(app);client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    monkeypatch.setattr(settings,'product_image_source','postgres')
    with SessionLocal() as db:
        product=db.scalar(select(Product));pid=product.public_id;sku=product.sku
        old_data=product.image_data;old_type=product.image_media_type
        product.image_data=b'order-photo';product.image_media_type='image/png'
        actor=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        access=db.get(OperatorAccess,actor.id);created=access is None
        previous=dict(access.permissions) if access else None
        if created:access=OperatorAccess(user_id=actor.id,exit_code='photo-permission-test',permissions={'orders':True});db.add(access)
        else:access.permissions={**previous,'orders':True}
        db.commit()
        try:
            paths=[f'/api/v1/products/by-sku/{sku}/image',f'/api/v1/products/{pid}/image',f'/api/v1/products/by-sku/{sku}/visual']
            for path in paths:
                assert client.get(path).status_code==200
                assert TestClient(app).get(path).status_code==401
            access.permissions={**access.permissions,'orders':False};db.commit()
            for path in paths:assert client.get(path).status_code==403
        finally:
            product.image_data=old_data;product.image_media_type=old_type
            if created:db.delete(access)
            else:access.permissions=previous
            db.commit()
