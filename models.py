import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base

class Store(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    default_name = Column(String, unique=True, index=True)

class StorePrice(Base):
    __tablename__ = "store_prices"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    unit_price = Column(Float)
    unit_type = Column(String)  # kg, l, db
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

    store = relationship("Store")
    product = relationship("Product")

class Receipt(Base):
    __tablename__ = "receipts"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"))
    total_amount = Column(Float)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    image_path = Column(String, nullable=True)

    store = relationship("Store")