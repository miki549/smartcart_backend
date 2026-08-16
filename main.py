import os
import io
import asyncio
import datetime
import uuid
from typing import List, Optional
from PIL import Image, ImageOps

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

import models
import schemas
import crud
import auth
import receipt_service
from database import engine, get_db

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
RECEIPT_PROCESSING_LOCK = asyncio.Lock()

models.Base.metadata.create_all(bind=engine)


def ensure_receipt_purchase_column():
    inspector = inspect(engine)
    columns = [column["name"] for column in inspector.get_columns("receipts")]
    if "purchased_at" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE receipts ADD COLUMN purchased_at TIMESTAMP"))


ensure_receipt_purchase_column()

app = FastAPI(
    title="SmartCart API",
    description="Multi-user Backend API boltok, termékek és blokkok kezelésére",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "online", "message": "SmartCart Multi-user API sikeresen fut!"}

# ================= AUTH VÉGPONTOK =================
@app.post("/auth/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
def register(user_data: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = crud.get_user_by_username(db, user_data.username.strip())
    if existing:
        raise HTTPException(status_code=400, detail="Ez a felhasználónév már foglalt.")
    if len(user_data.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="A jelszónak legalább 4 karakter hosszúnak kell lennie.")
    return crud.create_user(db, user_data)

@app.post("/auth/login", response_model=schemas.TokenResponse, tags=["Auth"])
def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, user_data.username.strip())
    if not user or not auth.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Hibás felhasználónév vagy jelszó.")
    
    token = auth.create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username
    }

@app.get("/auth/me", response_model=schemas.UserResponse, tags=["Auth"])
def get_current_user_profile(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@app.put("/auth/change-password", tags=["Auth"])
def change_password(
    payload: schemas.PasswordChangeRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not auth.verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="A jelenlegi jelszó helytelen.")
    if len(payload.new_password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Az új jelszónak legalább 4 karakter hosszúnak kell lennie.")

    crud.update_user_password(db, current_user, payload.new_password.strip())
    return {"message": "Jelszó sikeresen frissítve."}

@app.post("/auth/delete-account", tags=["Auth"])
def delete_account(
    payload: schemas.AccountDeleteRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not auth.verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="A jelszó helytelen, a fiók nem törölhető.")

    crud.delete_user(db, current_user)
    return {"message": "Fiók sikeresen törölve."}

# ================= KÖZÖS ADATOK (BOLTOK, TERMÉKEK, ÁRAK) =================
@app.get("/stores", response_model=List[schemas.StoreResponse], tags=["Stores"])
def list_stores(db: Session = Depends(get_db)):
    return crud.get_stores(db)

@app.get("/products", response_model=List[schemas.ProductResponse], tags=["Products"])
def list_products(db: Session = Depends(get_db)):
    return crud.get_products(db)


@app.get("/catalog/version", response_model=schemas.CatalogVersionResponse, tags=["Products", "Stores"])
def get_catalog_version(db: Session = Depends(get_db)):
    return crud.get_catalog_version(db)

@app.post("/store-prices", response_model=schemas.StorePriceResponse, tags=["Prices"])
def set_store_price(price: schemas.StorePriceCreate, db: Session = Depends(get_db)):
    return crud.upsert_store_price(
        db, 
        store_id=price.store_id, 
        product_id=price.product_id, 
        unit_price=price.unit_price, 
        unit_type=price.unit_type
    )

@app.post("/cart/estimate", response_model=schemas.CartEstimateResponse, tags=["Cart"])
def estimate_cart(request: schemas.CartEstimateRequest, db: Session = Depends(get_db)):
    return crud.calculate_cart(db, request)

# ================= PRIVÁT BLOKK ÉS ELŐZMÉNY VÉGPONTOK =================
@app.post("/receipts/upload", response_model=schemas.ReceiptProcessResponse, tags=["Receipts"])
async def upload_receipt(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    saved_filename = f"receipt_{uuid.uuid4().hex}.jpg"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)
    
    try:
        image = Image.open(io.BytesIO(contents))
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        image.save(saved_path, format="JPEG", quality=95)
    except Exception as e:
        print(f"⚠️ Képfeldolgozási figyelmeztetés: {e}")
        with open(saved_path, "wb") as f:
            f.write(contents)

    try:
        async with RECEIPT_PROCESSING_LOCK:
            parsed_data = await asyncio.to_thread(receipt_service.analyze_receipt_image, saved_path)
        print(f"🤖 [GEMINI - Felhasználó: {current_user.username}]:", parsed_data)
    except Exception as e:
        print(f"❌ Gemini hiba: {e}")
        raise HTTPException(status_code=500, detail=f"Nem sikerült beolvasni a blokkot: {str(e)}")

    receipt, store = crud.save_processed_receipt(
        db=db,
        user_id=current_user.id,
        parsed_data=parsed_data,
        image_path=saved_path
    )

    return {
        "receipt_id": receipt.id,
        "store_id": store.id,
        "store_name": store.name,
        "total_amount": receipt.total_amount,
        "date": str(parsed_data.get("date") or (receipt.created_at.date() if hasattr(receipt, 'created_at') and receipt.created_at else datetime.date.today())),
        "items_count": len(receipt.items),
        "items": receipt.items
    }

@app.get("/receipts/history", response_model=List[schemas.ReceiptHistoryResponse], tags=["Receipts"])
def get_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_receipt_history(db, current_user.id)

@app.put("/receipts/{receipt_id}", response_model=schemas.ReceiptHistoryResponse, tags=["Receipts"])
def update_receipt_endpoint(
    receipt_id: int, 
    req: schemas.ReceiptUpdateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    updated = crud.update_receipt(db, current_user.id, receipt_id, req)
    if not updated:
        raise HTTPException(status_code=404, detail="A blokk nem található vagy nincs jogosultságod módosítani.")
    return updated

@app.delete("/receipts/{receipt_id}", status_code=204, tags=["Receipts"])
def delete_receipt_endpoint(
    receipt_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    success = crud.delete_receipt(db, current_user.id, receipt_id)
    if not success:
        raise HTTPException(status_code=404, detail="A blokk nem található vagy nincs jogosultságod törölni.")
    return None