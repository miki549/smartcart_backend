from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

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

# --- Bolti ár sémák ---
class StorePriceBase(BaseModel):
    store_id: int
    product_id: int
    unit_price: float
    unit_type: str  # kg, l, db

class StorePriceCreate(StorePriceBase):
    pass

class StorePriceResponse(StorePriceBase):
    id: int
    last_updated: datetime
    product: ProductResponse

    class Config:
        from_attributes = True

# --- Bevásárlólista tétel kalkulációhoz ---
class CartItemRequest(BaseModel):
    product_id: int
    quantity: float  # pl. 2.5 kg vagy 3 db

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

class CartEstimateResponse(BaseModel):
    store_id: int
    store_name: str
    items: List[CartItemEstimateResponse]
    estimated_total: float
    has_unknown_prices: bool
    # --- Blokk elemzés sémák ---
class ReceiptItemParsed(BaseModel):
    product_name: str
    quantity: float
    unit_type: str  # kg, l, db, csomag
    unit_price: float
    total_price: float

class ReceiptProcessResponse(BaseModel):
    receipt_id: int
    store_name: str
    store_id: int
    total_amount: float
    date: Optional[str]
    items_count: int
    items: List[ReceiptItemParsed]