import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base

class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    prices = relationship("StorePrice", back_populates="store")
    receipts = relationship("Receipt", back_populates="store")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    default_name = Column(String, unique=True, index=True, nullable=False)

    prices = relationship("StorePrice", back_populates="product")


class StorePrice(Base):
    __tablename__ = "store_prices"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    unit_type = Column(String, default="db")
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

    store = relationship("Store", back_populates="prices")
    product = relationship("Product", back_populates="prices")


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    total_amount = Column(Float, nullable=False)
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    store = relationship("Store", back_populates="receipts")
    items = relationship("ReceiptItem", back_populates="receipt", cascade="all, delete-orphan")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Float, default=1.0)
    unit_type = Column(String, default="db")
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)

    receipt = relationship("Receipt", back_populates="items")