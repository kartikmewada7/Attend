from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# Connection pool tuned for fast response:
# - pool_size=5: keep 5 connections ready
# - max_overflow=10: allow 10 more under load
# - pool_pre_ping=True: auto-reconnect stale connections
# - pool_recycle=300: refresh connections every 5 min (avoids Supabase timeouts)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
