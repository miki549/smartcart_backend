import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    receipts = relationship("Receipt", back_populates="user", cascade="all, delete-orphan")


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)

    prices = relationship("StorePrice", back_populates="store", cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="store")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    default_name = Column(String(150), unique=True, index=True, nullable=False)

    prices = relationship("StorePrice", back_populates="product", cascade="all, delete-orphan")


class StorePrice(Base):
    __tablename__ = "store_prices"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    unit_price = Column(Float, nullable=False)
    unit_type = Column(String(20), default="db")
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

    store = relationship("Store", back_populates="prices")
    product = relationship("Product", back_populates="prices")


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # <-- Felhasználóhoz kötve
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    total_amount = Column(Float, nullable=False)
    image_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    purchased_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="receipts")
    store = relationship("Store", back_populates="receipts")
    items = relationship("ReceiptItem", back_populates="receipt", cascade="all, delete-orphan")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    product_name = Column(String(150), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_type = Column(String(20), default="db")
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)

    receipt = relationship("Receipt", back_populates="items")