from sqlalchemy.orm import Session
import models
import schemas

# --- Boltok ---
def get_stores(db: Session):
    return db.query(models.Store).all()

def create_store(db: Session, store: schemas.StoreCreate):
    db_store = models.Store(name=store.name)
    db.add(db_store)
    db.commit()
    db.refresh(db_store)
    return db_store

# --- Termékek ---
def get_products(db: Session):
    return db.query(models.Product).all()

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(default_name=product.default_name)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

# --- Ár lekérdezés / frissítés ---
def get_latest_price(db: Session, store_id: int, product_id: int):
    return db.query(models.StorePrice).filter(
        models.StorePrice.store_id == store_id,
        models.StorePrice.product_id == product_id
    ).first()

def upsert_store_price(db: Session, store_id: int, product_id: int, unit_price: float, unit_type: str):
    existing_price = get_latest_price(db, store_id, product_id)
    if existing_price:
        existing_price.unit_price = unit_price
        existing_price.unit_type = unit_type
        db.commit()
        db.refresh(existing_price)
        return existing_price
    else:
        new_price = models.StorePrice(
            store_id=store_id,
            product_id=product_id,
            unit_price=unit_price,
            unit_type=unit_type
        )
        db.add(new_price)
        db.commit()
        db.refresh(new_price)
        return new_price

# --- Kosárkalkuláció logikája ---
def calculate_cart(db: Session, request: schemas.CartEstimateRequest) -> schemas.CartEstimateResponse:
    store = db.query(models.Store).filter(models.Store.id == request.store_id).first()
    store_name = store.name if store else "Ismeretlen bolt"
    
    items_response = []
    estimated_total = 0.0
    has_unknown = False

    for item in request.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        prod_name = product.default_name if product else "Ismeretlen termék"
        
        price_entry = get_latest_price(db, request.store_id, item.product_id)
        
        if price_entry and price_entry.unit_price is not None:
            item_cost = price_entry.unit_price * item.quantity
            estimated_total += item_cost
            items_response.append(schemas.CartItemEstimateResponse(
                product_id=item.product_id,
                product_name=prod_name,
                quantity=item.quantity,
                unit_price=price_entry.unit_price,
                unit_type=price_entry.unit_type,
                total_item_price=item_cost,
                is_price_known=True
            ))
        else:
            has_unknown = True
            items_response.append(schemas.CartItemEstimateResponse(
                product_id=item.product_id,
                product_name=prod_name,
                quantity=item.quantity,
                unit_price=None,
                unit_type=None,
                total_item_price=None,
                is_price_known=False
            ))

    return schemas.CartEstimateResponse(
        store_id=request.store_id,
        store_name=store_name,
        items=items_response,
        estimated_total=round(estimated_total, 2),
        has_unknown_prices=has_unknown
    )
def save_processed_receipt(db: Session, parsed_data: dict, image_path: str):
    store_name = parsed_data.get("store_name", "Egyéb bolt")
    
    # 1. Bolt megkeresése vagy létrehozása
    store = db.query(models.Store).filter(models.Store.name.ilike(f"%{store_name}%")).first()
    if not store:
        store = models.Store(name=store_name)
        db.add(store)
        db.commit()
        db.refresh(store)

    # 2. Blokk fejléc mentése
    receipt = models.Receipt(
        store_id=store.id,
        total_amount=float(parsed_data.get("total_amount", 0.0)),
        image_path=image_path
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    # 3. Tételek és árak mentése / frissítése
    for item in parsed_data.get("items", []):
        prod_name = item.get("product_name", "").strip()
        if not prod_name:
            continue

        # Termék keresése vagy létrehozása
        product = db.query(models.Product).filter(models.Product.default_name.ilike(prod_name)).first()
        if not product:
            product = models.Product(default_name=prod_name)
            db.add(product)
            db.commit()
            db.refresh(product)

        # Ár frissítése az adott bolthoz
        upsert_store_price(
            db=db,
            store_id=store.id,
            product_id=product.id,
            unit_price=float(item.get("unit_price", item.get("total_price", 0.0))),
            unit_type=item.get("unit_type", "db")
        )

    return receipt, store