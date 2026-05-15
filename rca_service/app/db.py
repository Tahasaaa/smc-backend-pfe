import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_NAME = os.getenv("RCA_DB_NAME", "v2_rca_db")
DB_USER = os.getenv("RCA_DB_USER", "postgres")
DB_PASSWORD = os.getenv("RCA_DB_PASSWORD", "")
DB_HOST = os.getenv("RCA_DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("RCA_DB_PORT", "5432")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()