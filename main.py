import os
import shutil
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

import models
import schemas
import crud
from database import engine, get_db
from receipt_service import analyze_receipt_image

# Feltöltési mappa létrehozása, ha még nem létezik
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Létrehozza a táblákat az adatbázisban indításkor
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SmartCart API",
    description="Backend API a boltok, termékek és blokkok kezelésére",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"status": "online", "message": "SmartCart API sikeresen fut!"}

# --- Boltok végpontjai ---
@app.get("/stores", response_model=List[schemas.StoreResponse], tags=["Stores"])
def list_stores(db: Session = Depends(get_db)):
    return crud.get_stores(db)

@app.post("/stores", response_model=schemas.StoreResponse, status_code=status.HTTP_201_CREATED, tags=["Stores"])
def add_store(store: schemas.StoreCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Store).filter(models.Store.name.ilike(store.name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"A(z) '{store.name}' nevű bolt már létezik az adatbázisban!"
        )
    return crud.create_store(db, store)

# --- Termékek végpontjai ---
@app.get("/products", response_model=List[schemas.ProductResponse], tags=["Products"])
def list_products(db: Session = Depends(get_db)):
    return crud.get_products(db)

@app.post("/products", response_model=schemas.ProductResponse, status_code=status.HTTP_201_CREATED, tags=["Products"])
def add_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Product).filter(models.Product.default_name.ilike(product.default_name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"A(z) '{product.default_name}' nevű termék már létezik az adatbázisban!"
        )
    return crud.create_product(db, product)

# --- Bolti árak rögzítése ---
@app.post("/store-prices", response_model=schemas.StorePriceResponse, tags=["Prices"])
def set_store_price(price: schemas.StorePriceCreate, db: Session = Depends(get_db)):
    return crud.upsert_store_price(
        db, 
        store_id=price.store_id, 
        product_id=price.product_id, 
        unit_price=price.unit_price, 
        unit_type=price.unit_type
    )

# --- Kosárkalkuláció ---
@app.post("/cart/estimate", response_model=schemas.CartEstimateResponse, tags=["Cart"])
def estimate_cart(request: schemas.CartEstimateRequest, db: Session = Depends(get_db)):
    return crud.calculate_cart(db, request)

@app.post("/receipts/upload", response_model=schemas.ReceiptProcessResponse, tags=["Receipts"])
async def upload_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Fájl mentése lemezre
    file_location = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # AI elemzés
        parsed_data = analyze_receipt_image(file_location)
        
        # Adatbázis mentés és árak frissítése
        receipt, store = crud.save_processed_receipt(db, parsed_data, file_location)

        return schemas.ReceiptProcessResponse(
            receipt_id=receipt.id,
            store_name=store.name,
            store_id=store.id,
            total_amount=receipt.total_amount,
            date=parsed_data.get("date"),
            items_count=len(parsed_data.get("items", [])),
            items=[schemas.ReceiptItemParsed(**item) for item in parsed_data.get("items", [])]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hiba történt a blokk feldolgozása közben: {str(e)}"
        )