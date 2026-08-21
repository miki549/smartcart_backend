import datetime
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
import models
import schemas
import auth

MAX_PRICE_UPDATE_AGE_DAYS = 30

def _get_utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

def _parse_purchase_datetime(raw_value):
    if raw_value is None:
        return None

    if isinstance(raw_value, datetime.datetime):
        if raw_value.tzinfo is not None:
            return raw_value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return raw_value

    text = str(raw_value).strip()
    if not text:
        return None

    iso_candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is not None:
            return parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        pass

    for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed_date = datetime.datetime.strptime(text, pattern)
            return parsed_date
        except ValueError:
            continue

    return None

def _validate_and_sanitize_date(parsed_date: datetime.datetime) -> datetime.datetime:
    now = _get_utc_now()
    if parsed_date is None:
        return now
    if parsed_date > now + datetime.timedelta(days=1):
        return now
    return parsed_date

# --- Felhasználók ---
def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserRegister):
    hashed_pwd = auth.get_password_hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_pwd)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_password(db: Session, user: models.User, new_password: str):
    user.hashed_password = auth.get_password_hash(new_password)
    db.commit()
    db.refresh(user)
    return user

def delete_user(db: Session, user: models.User):
    db.delete(user)
    db.commit()
    return True

# --- Boltok ---
def get_stores(db: Session):
    # Visszaadjuk az összes rögzített boltot
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

def get_catalog_version(db: Session) -> schemas.CatalogVersionResponse:
    store_count = db.query(func.count(models.Store.id)).scalar() or 0
    store_max_id = db.query(func.max(models.Store.id)).scalar() or 0

    product_count = db.query(func.count(models.Product.id)).scalar() or 0
    product_max_id = db.query(func.max(models.Product.id)).scalar() or 0

    latest_price_update = db.query(func.max(models.StorePrice.last_updated)).scalar()
    latest_price_epoch = int(latest_price_update.timestamp()) if latest_price_update else 0

    version = f"s:{store_count}:{store_max_id}|p:{product_count}:{product_max_id}|pr:{latest_price_epoch}"
    return schemas.CatalogVersionResponse(version=version)

# --- Árak ---
def get_latest_price(db: Session, store_id: int, product_id: int):
    return db.query(models.StorePrice).filter(
        models.StorePrice.store_id == store_id,
        models.StorePrice.product_id == product_id
    ).first()

def upsert_store_price(
    db: Session, 
    store_id: int, 
    product_id: int, 
    unit_price: float, 
    unit_type: str,
    effective_date: datetime.datetime = None
):
    now = _get_utc_now()
    target_date = _validate_and_sanitize_date(effective_date)

    age = now - target_date
    if age.days > MAX_PRICE_UPDATE_AGE_DAYS:
        return get_latest_price(db, store_id, product_id)

    existing_price = get_latest_price(db, store_id, product_id)
    if existing_price:
        if existing_price.last_updated is None or target_date >= existing_price.last_updated:
            existing_price.unit_price = unit_price
            existing_price.unit_type = unit_type
            existing_price.last_updated = target_date
            db.commit()
            db.refresh(existing_price)
        return existing_price
    else:
        new_price = models.StorePrice(
            store_id=store_id,
            product_id=product_id,
            unit_price=unit_price,
            unit_type=unit_type,
            last_updated=target_date
        )
        db.add(new_price)
        db.commit()
        db.refresh(new_price)
        return new_price

# --- Kosár kalkuláció ---
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
                is_price_known=True,
                last_updated=price_entry.last_updated
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
                is_price_known=False,
                last_updated=None
            ))

    return schemas.CartEstimateResponse(
        store_id=request.store_id,
        store_name=store_name,
        items=items_response,
        estimated_total=round(estimated_total, 2),
        has_unknown_prices=has_unknown
    )

# --- Blokk mentése ---
def save_processed_receipt(db: Session, user_id: int, parsed_data: dict, image_path: str):
    store_name = parsed_data.get("store_name", "Egyéb bolt").strip()
    
    store = db.query(models.Store).filter(models.Store.name.ilike(f"%{store_name}%")).first()
    if not store:
        store = models.Store(name=store_name)
        db.add(store)
        db.commit()
        db.refresh(store)

    parsed_purchase_time = _parse_purchase_datetime(parsed_data.get("date"))
    receipt = models.Receipt(
        user_id=user_id,
        store_id=store.id,
        total_amount=float(parsed_data.get("total_amount", 0.0)),
        image_path=image_path,
        created_at=_get_utc_now(),
        purchased_at=parsed_purchase_time
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    price_effective_date = parsed_purchase_time or receipt.created_at

    for item in parsed_data.get("items", []):
        prod_name = item.get("product_name", "").strip()
        if not prod_name:
            continue

        unit_p = float(item.get("unit_price", item.get("total_price", 0.0)))
        tot_p = float(item.get("total_price", unit_p))
        qty = float(item.get("quantity", 1.0))
        u_type = item.get("unit_type", "db")

        receipt_item = models.ReceiptItem(
            receipt_id=receipt.id,
            product_name=prod_name,
            quantity=qty,
            unit_type=u_type,
            unit_price=unit_p,
            total_price=tot_p
        )
        db.add(receipt_item)

        product = db.query(models.Product).filter(models.Product.default_name.ilike(prod_name)).first()
        if not product:
            product = models.Product(default_name=prod_name)
            db.add(product)
            db.commit()
            db.refresh(product)

        upsert_store_price(
            db=db,
            store_id=store.id,
            product_id=product.id,
            unit_price=unit_p,
            unit_type=u_type,
            effective_date=price_effective_date
        )

    db.commit()
    db.refresh(receipt)
    return receipt, store

# --- Vásárlási előzmények lekérése ---
def get_receipt_history(db: Session, user_id: int):
    receipts = db.query(models.Receipt).filter(models.Receipt.user_id == user_id).order_by(models.Receipt.id.desc()).all()
    result = []
    for r in receipts:
        result.append({
            "id": r.id,
            "store_name": r.store.name if r.store else "Ismeretlen bolt",
            "total_amount": r.total_amount,
            "created_at": r.created_at or _get_utc_now(),
            "purchased_at": r.purchased_at,
            "items": r.items or []
        })
    return result

def update_receipt(db: Session, user_id: int, receipt_id: int, req: schemas.ReceiptUpdateRequest):
    receipt = db.query(models.Receipt).filter(models.Receipt.id == receipt_id, models.Receipt.user_id == user_id).first()
    if not receipt:
        return None

    new_store_name = req.store_name.strip() if req.store_name else "Egyéb bolt"

    store = db.query(models.Store).filter(models.Store.name.ilike(new_store_name)).first()
    if not store:
        store = models.Store(name=new_store_name)
        db.add(store)
        db.commit()
        db.refresh(store)

    receipt.store_id = store.id

    db.query(models.ReceiptItem).filter(models.ReceiptItem.receipt_id == receipt_id).delete()

    normalized_price_map = {}
    for req_item in req.items:
        normalized_name = req_item.product_name.strip().lower()
        if normalized_name:
            normalized_price_map[normalized_name] = req_item.unit_price

    if req.purchased_at is not None:
        receipt.purchased_at = _parse_purchase_datetime(req.purchased_at)

    price_effective_date = receipt.purchased_at or receipt.created_at or _get_utc_now()

    calculated_total = 0.0
    for item in req.items:
        p_name = item.product_name.strip()
        if not p_name:
            continue

        normalized_name = p_name.lower()
        effective_unit_price = normalized_price_map.get(normalized_name, item.unit_price)

        tot_p = item.total_price if item.total_price > 0 else (item.quantity * effective_unit_price)
        calculated_total += tot_p

        receipt_item = models.ReceiptItem(
            receipt_id=receipt.id,
            product_name=p_name,
            quantity=item.quantity,
            unit_type=item.unit_type,
            unit_price=effective_unit_price,
            total_price=tot_p
        )
        db.add(receipt_item)

        product = db.query(models.Product).filter(models.Product.default_name.ilike(p_name)).first()
        if not product:
            product = models.Product(default_name=p_name)
            db.add(product)
            db.commit()
            db.refresh(product)

        upsert_store_price(
            db=db,
            store_id=store.id,
            product_id=product.id,
            unit_price=effective_unit_price,
            unit_type=item.unit_type,
            effective_date=price_effective_date
        )

    receipt.total_amount = req.total_amount if req.total_amount and req.total_amount > 0 else calculated_total

    db.commit()
    db.refresh(receipt)

    return {
        "id": receipt.id,
        "store_name": store.name,
        "total_amount": receipt.total_amount,
        "created_at": receipt.created_at or _get_utc_now(),
        "purchased_at": receipt.purchased_at,
        "items": receipt.items
    }

def delete_receipt(db: Session, user_id: int, receipt_id: int) -> bool:
    receipt = db.query(models.Receipt).filter(models.Receipt.id == receipt_id, models.Receipt.user_id == user_id).first()
    if not receipt:
        return False

    # Csak magát a blokk entitást töröljük, a boltok, termékek és árak megmaradnak!
    db.delete(receipt)
    db.commit()
    return True

def compare_all_stores_cart(db: Session, items: List[schemas.CartItemRequest]) -> schemas.MultiStoreEstimateResponse:
    stores = get_stores(db)
    if not stores or not items:
        return schemas.MultiStoreEstimateResponse(results=[])

    results: List[schemas.StoreComparisonResult] = []

    for store in stores:
        total = 0.0
        missing_count = 0
        for item in items:
            price_entry = get_latest_price(db, store.id, item.product_id)
            if price_entry and price_entry.unit_price is not None:
                total += price_entry.unit_price * item.quantity
            else:
                missing_count += 1
        
        results.append(schemas.StoreComparisonResult(
            store_id=store.id,
            store_name=store.name,
            estimated_total=round(total, 2),
            is_complete=(missing_count == 0),
            missing_items_count=missing_count
        ))

    complete_results = [r for r in results if r.is_complete]
    best_store = None

    if complete_results:
        complete_results.sort(key=lambda x: x.estimated_total)
        best_store = complete_results[0]
        for r in results:
            if r.is_complete:
                r.price_difference_from_best = round(r.estimated_total - best_store.estimated_total, 2)
    
    results.sort(key=lambda x: (not x.is_complete, x.estimated_total))

    return schemas.MultiStoreEstimateResponse(
        best_store_id=best_store.store_id if best_store else None,
        best_store_name=best_store.store_name if best_store else None,
        results=results
    )

def get_spending_analytics(db: Session, user_id: int) -> schemas.MonthlySpendingStats:
    now = _get_utc_now()
    receipts = db.query(models.Receipt).filter(models.Receipt.user_id == user_id).all()
    
    current_month_total = 0.0
    store_totals = {}

    for r in receipts:
        dt = r.purchased_at or r.created_at or now
        if dt.year == now.year and dt.month == now.month:
            current_month_total += r.total_amount
            s_name = r.store.name if r.store else "Egyéb bolt"
            store_totals[s_name] = store_totals.get(s_name, 0.0) + r.total_amount

    breakdown = []
    if current_month_total > 0:
        for s_name, amt in sorted(store_totals.items(), key=lambda x: x[1], reverse=True):
            pct = round((amt / current_month_total) * 100, 1)
            breakdown.append(schemas.StoreSpendingBreakdown(
                store_name=s_name,
                total_spent=round(amt, 2),
                percentage=pct
            ))

    months_hu = ["Január", "Február", "Március", "Április", "Május", "Június", "Július", "Augusztus", "Szeptember", "Október", "November", "December"]
    current_month_name = f"{now.year}. {months_hu[now.month - 1]}"

    return schemas.MonthlySpendingStats(
        current_month_name=current_month_name,
        current_month_total=round(current_month_total, 2),
        total_receipts_count=len(receipts),
        store_breakdown=breakdown
    )