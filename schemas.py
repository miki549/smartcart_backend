from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- Auth & Felhasználó sémák ---
class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class AccountDeleteRequest(BaseModel):
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str

# --- Bolt sémák ---
class StoreBase(BaseModel):
    name: str

class StoreCreate(StoreBase):
    pass

class StoreResponse(StoreBase):
    id: int

    class Config:
        from_attributes = True

# --- Termék sémák ---
class ProductBase(BaseModel):
    default_name: str

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True


class CatalogVersionResponse(BaseModel):
    version: str

# --- Bolti ár sémák ---
class StorePriceBase(BaseModel):
    store_id: int
    product_id: int
    unit_price: float
    unit_type: str

class StorePriceCreate(StorePriceBase):
    pass

class StorePriceResponse(StorePriceBase):
    id: int
    last_updated: datetime
    product: ProductResponse

    class Config:
        from_attributes = True

# --- Kosárkalkuláció ---
class CartItemRequest(BaseModel):
    product_id: int
    quantity: float

class CartEstimateRequest(BaseModel):
    store_id: int
    items: List[CartItemRequest]

class CartItemEstimateResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: float
    unit_price: Optional[float] = None
    unit_type: Optional[str] = None
    total_item_price: Optional[float] = None
    is_price_known: bool
    last_updated: Optional[datetime] = None

class CartEstimateResponse(BaseModel):
    store_id: int
    store_name: str
    items: List[CartItemEstimateResponse]
    estimated_total: float
    has_unknown_prices: bool

# --- Blokk elemzés & Előzmény sémák ---
class ReceiptItemParsed(BaseModel):
    product_name: str
    quantity: float
    unit_type: str = "db"
    unit_price: float
    total_price: float

    class Config:
        from_attributes = True

class ReceiptProcessResponse(BaseModel):
    receipt_id: int
    store_id: int
    store_name: str
    total_amount: float
    date: Optional[str] = None
    items_count: int
    items: List[ReceiptItemParsed]

    class Config:
        from_attributes = True

class ReceiptDetailItem(BaseModel):
    id: int
    product_name: str
    quantity: float
    unit_type: str
    unit_price: float
    total_price: float

    class Config:
        from_attributes = True

class ReceiptHistoryResponse(BaseModel):
    id: int
    store_name: str
    total_amount: float
    created_at: datetime
    purchased_at: Optional[datetime] = None
    items: List[ReceiptDetailItem]

    class Config:
        from_attributes = True

class ReceiptItemUpdate(BaseModel):
    id: Optional[int] = None
    product_name: str
    quantity: float
    unit_type: str = "db"
    unit_price: float
    total_price: float

class ReceiptUpdateRequest(BaseModel):
    store_name: str
    total_amount: Optional[float] = None
    purchased_at: Optional[datetime] = None
    items: List[ReceiptItemUpdate]

# --- Bolt-összehasonlítás sémák ---
class StoreComparisonResult(BaseModel):
    store_id: int
    store_name: str
    estimated_total: float
    is_complete: bool  # Minden termék ára ismert-e
    missing_items_count: int
    price_difference_from_best: float = 0.0

class MultiStoreEstimateResponse(BaseModel):
    best_store_id: Optional[int] = None
    best_store_name: Optional[str] = None
    results: List[StoreComparisonResult]

# --- Költési statisztika sémák ---
class StoreSpendingBreakdown(BaseModel):
    store_name: str
    total_spent: float
    percentage: float

class MonthlySpendingStats(BaseModel):
    current_month_name: str
    current_month_total: float
    total_receipts_count: int
    store_breakdown: List[StoreSpendingBreakdown]