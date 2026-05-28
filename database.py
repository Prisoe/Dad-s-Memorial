from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use /data (Render persistent disk) if available, else local
DATA_DIR = "/data" if os.path.exists("/data") else BASE_DIR
DATABASE_URL = f"sqlite:///{DATA_DIR}/memorial.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Tribute(Base):
    __tablename__ = "tributes"
    id        = Column(Integer, primary_key=True, index=True)
    name      = Column(String(100), nullable=False)
    location  = Column(String(100), nullable=True)
    relation  = Column(String(100), nullable=True)
    message   = Column(Text, nullable=False)
    approved  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Photo(Base):
    __tablename__ = "photos"
    id         = Column(Integer, primary_key=True, index=True)
    filename   = Column(String(255), nullable=False)
    caption    = Column(String(255), nullable=True)
    sort_order = Column(Integer, default=0)
    active     = Column(Boolean, default=True)
    bg_rotation = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Video(Base):
    __tablename__ = "videos"
    id         = Column(Integer, primary_key=True, index=True)
    url        = Column(String(500), nullable=False)
    title      = Column(String(200), nullable=True)
    sort_order = Column(Integer, default=0)
    active     = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    id         = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(50), nullable=False, index=True)
    action     = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
