import os
import uuid
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
import crud
import auth
import receipt_service
from database import engine, get_db

# Táblák létrehozása
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="SmartCart API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Hitelesítés (Auth) ---

@app.post("/auth/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: schemas.UserRegister, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db, username=user_data.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Ez a felhasználónév már foglalt.")
    return crud.create_user(db, user_data)

@app.post("/auth/login", response_model=schemas.Token)
def login(login_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, username=login_data.username)
    if not user or not auth.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hibás felhasználónév vagy jelszó."
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}

@app.post("/auth/change-password")
def change_password(
    req: schemas.PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not auth.verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="A jelenlegi jelszó helytelen.")
    crud.update_user_password(db, current_user, req.new_password)
    return {"message": "A jelszó sikeresen módosítva."}

@app.post("/auth/delete-account")
def delete_account(
    req: schemas.AccountDeleteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not auth.verify_password(req.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="A megadott jelszó helytelen.")
    crud.delete_user(db, current_user)
    return {"message": "A fiók és a hozzá tartozó adatok törölve."}

# --- Katalógus (Boltok, Termékek, Verzió) ---

@app.get("/catalog/version", response_model=schemas.CatalogVersionResponse)
def get_catalog_version(db: Session = Depends(get_db)):
    return crud.get_catalog_version(db)

@app.get("/stores", response_model=List[schemas.StoreResponse])
def get_stores(db: Session = Depends(get_db)):
    return crud.get_stores(db)

@app.get("/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return crud.get_products(db)

# --- Kosár becslés ---

@app.post("/cart/estimate", response_model=schemas.CartEstimateResponse)
def estimate_cart(req: schemas.CartEstimateRequest, db: Session = Depends(get_db)):
    return crud.calculate_cart(db, req)

@app.post("/cart/compare-all", response_model=schemas.MultiStoreEstimateResponse)
def compare_all_stores(req: schemas.CartEstimateRequest, db: Session = Depends(get_db)):
    return crud.compare_all_stores_cart(db, req.items)

# --- Nyugták / Blokkok kezelése ---

@app.post("/receipts/upload")
async def upload_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    filename = f"receipt_{current_user.id}_{uuid.uuid4().hex}_{file.filename}"
    file_location = os.path.join(UPLOAD_DIR, filename)

    with open(file_location, "wb+") as f:
        f.write(await file.read())

    try:
        parsed_data = receipt_service.analyze_receipt_image(file_location)

        is_receipt = parsed_data.get("is_receipt", False)
        items = parsed_data.get("items", [])
        total_amount = float(parsed_data.get("total_amount") or 0.0)

        # Ha a kép nem bolti blokk, töröljük a fájlt és hibát dobunk
        if not is_receipt or (len(items) == 0 and total_amount <= 0):
            if os.path.exists(file_location):
                os.remove(file_location)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A feltöltött képen nem található érvényes bolti blokk vagy nyugta."
            )

        receipt, store = crud.save_processed_receipt(
            db=db,
            user_id=current_user.id,
            parsed_data=parsed_data,
            image_path=file_location
        )

        return {
            "storeName": store.name,
            "totalAmount": receipt.total_amount,
            "receiptId": receipt.id
        }

    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hiba a blokk feldolgozása közben: {str(e)}"
        )

@app.get("/receipts/history", response_model=List[schemas.ReceiptHistoryResponse])
def get_receipt_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud.get_receipt_history(db, current_user.id)

@app.put("/receipts/{receipt_id}", response_model=schemas.ReceiptHistoryResponse)
def update_receipt(
    receipt_id: int,
    req: schemas.ReceiptUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    updated = crud.update_receipt(db, current_user.id, receipt_id, req)
    if not updated:
        raise HTTPException(status_code=404, detail="A blokk nem található.")
    return updated

@app.delete("/receipts/{receipt_id}")
def delete_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    success = crud.delete_receipt(db, current_user.id, receipt_id)
    if not success:
        raise HTTPException(status_code=404, detail="A blokk nem található.")
    return {"message": "Blokk sikeresen törölve."}

# --- Statisztika ---

@app.get("/analytics", response_model=schemas.MonthlySpendingStats)
def get_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud.get_spending_analytics(db, current_user.id)