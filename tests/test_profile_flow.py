import os
import datetime

os.environ["DATABASE_URL"] = "sqlite:///./test_smartcart_profile.db"

from fastapi.testclient import TestClient

import models
import schemas
import crud
from database import engine, Base
from main import app


Base.metadata.create_all(bind=engine)
client = TestClient(app)


def setup_function():
    models.User.__table__.drop(bind=engine, checkfirst=True)
    models.Store.__table__.drop(bind=engine, checkfirst=True)
    models.Product.__table__.drop(bind=engine, checkfirst=True)
    models.StorePrice.__table__.drop(bind=engine, checkfirst=True)
    models.Receipt.__table__.drop(bind=engine, checkfirst=True)
    models.ReceiptItem.__table__.drop(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)


def test_change_password_and_delete_account():
    register = client.post("/auth/register", json={"username": "alice", "password": "pw123"})
    assert register.status_code == 201, register.text

    login = client.post("/auth/login", json={"username": "alice", "password": "pw123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    response = client.put(
        "/auth/change-password",
        json={"current_password": "pw123", "new_password": "newpw456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Jelszó sikeresen frissítve."

    second_login = client.post("/auth/login", json={"username": "alice", "password": "newpw456"})
    assert second_login.status_code == 200, second_login.text
    new_token = second_login.json()["access_token"]

    delete_response = client.post(
        "/auth/delete-account",
        json={"password": "newpw456"},
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["message"] == "Fiók sikeresen törölve."

    profile = client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert profile.status_code == 401


def test_cart_uses_latest_price_but_keeps_history_unchanged():
    db = next(iter(__import__('database').get_db()))

    store = models.Store(name="Tesco")
    db.add(store)
    db.commit(); db.refresh(store)

    product = models.Product(default_name="Alma")
    db.add(product)
    db.commit(); db.refresh(product)

    user = models.User(username="history_user", hashed_password="hash")
    db.add(user)
    db.commit(); db.refresh(user)

    old_price = crud.upsert_store_price(db, store.id, product.id, 450.0, "kg")
    old_price.last_updated = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    db.commit()

    receipt = models.Receipt(user_id=user.id, store_id=store.id, total_amount=900.0)
    db.add(receipt)
    db.commit(); db.refresh(receipt)

    old_item = models.ReceiptItem(
        receipt_id=receipt.id,
        product_name=product.default_name,
        quantity=2.0,
        unit_type="kg",
        unit_price=450.0,
        total_price=900.0,
    )
    db.add(old_item)
    db.commit(); db.refresh(old_item)

    new_price = crud.upsert_store_price(db, store.id, product.id, 620.0, "kg")
    assert new_price.last_updated >= old_price.last_updated

    estimate = crud.calculate_cart(db, schemas.CartEstimateRequest(
        store_id=store.id,
        items=[schemas.CartItemRequest(product_id=product.id, quantity=2.0)]
    ))

    assert estimate.items[0].unit_price == 620.0
    assert estimate.items[0].last_updated is not None
    assert db.query(models.ReceiptItem).filter(models.ReceiptItem.id == old_item.id).first().unit_price == 450.0


def test_catalog_version_changes_on_catalog_and_price_updates():
    db = next(iter(__import__('database').get_db()))

    v1 = crud.get_catalog_version(db).version

    store = models.Store(name="Aldi")
    db.add(store)
    db.commit(); db.refresh(store)

    product = models.Product(default_name="Tej")
    db.add(product)
    db.commit(); db.refresh(product)

    v2 = crud.get_catalog_version(db).version
    assert v2 != v1

    before_price_update = crud.get_catalog_version(db).version
    crud.upsert_store_price(db, store.id, product.id, 500.0, "db")
    after_price_update = crud.get_catalog_version(db).version
    assert after_price_update != before_price_update


def test_update_receipt_can_modify_purchase_datetime():
    db = next(iter(__import__('database').get_db()))

    store = models.Store(name="Lidl")
    db.add(store)
    db.commit(); db.refresh(store)

    user = models.User(username="date_editor", hashed_password="hash")
    db.add(user)
    db.commit(); db.refresh(user)

    receipt = models.Receipt(user_id=user.id, store_id=store.id, total_amount=1000.0)
    db.add(receipt)
    db.commit(); db.refresh(receipt)

    db.add(models.ReceiptItem(
        receipt_id=receipt.id,
        product_name="Kenyér",
        quantity=1.0,
        unit_type="db",
        unit_price=1000.0,
        total_price=1000.0,
    ))
    db.commit()

    purchase_time = datetime.datetime(2026, 8, 10, 9, 30, 0)
    update_payload = schemas.ReceiptUpdateRequest(
        store_name="Lidl",
        total_amount=1000.0,
        purchased_at=purchase_time,
        items=[schemas.ReceiptItemUpdate(
            product_name="Kenyér",
            quantity=1.0,
            unit_type="db",
            unit_price=1000.0,
            total_price=1000.0,
        )]
    )

    updated = crud.update_receipt(db, user.id, receipt.id, update_payload)
    assert updated is not None
    assert updated["purchased_at"] is not None
    assert updated["purchased_at"].year == 2026
    assert updated["purchased_at"].month == 8
    assert updated["purchased_at"].day == 10


def test_update_receipt_syncs_duplicate_product_prices():
    db = next(iter(__import__('database').get_db()))

    store = models.Store(name="Spar")
    db.add(store)
    db.commit(); db.refresh(store)

    user = models.User(username="dup_price_user", hashed_password="hash")
    db.add(user)
    db.commit(); db.refresh(user)

    receipt = models.Receipt(user_id=user.id, store_id=store.id, total_amount=0.0)
    db.add(receipt)
    db.commit(); db.refresh(receipt)

    req = schemas.ReceiptUpdateRequest(
        store_name="Spar",
        total_amount=0.0,
        purchased_at=None,
        items=[
            schemas.ReceiptItemUpdate(
                product_name="Tej",
                quantity=1.0,
                unit_type="db",
                unit_price=450.0,
                total_price=450.0,
            ),
            schemas.ReceiptItemUpdate(
                product_name="Tej",
                quantity=2.0,
                unit_type="db",
                unit_price=299.0,
                total_price=598.0,
            ),
        ],
    )

    updated = crud.update_receipt(db, user.id, receipt.id, req)
    assert updated is not None

    saved_items = db.query(models.ReceiptItem).filter(models.ReceiptItem.receipt_id == receipt.id).all()
    assert len(saved_items) == 2
    assert saved_items[0].unit_price == 299.0
    assert saved_items[1].unit_price == 299.0
