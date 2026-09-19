"""MySQL connection layer for PortPulse, using SQLAlchemy + PyMySQL.

Reads connection settings from environment variables (.env).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger(__name__)

load_dotenv(override=True)


DB_USER = quote_plus(os.getenv("MYSQL_USER", "root"))
DB_PASSWORD = quote_plus(os.getenv("MYSQL_PASSWORD", "Jigar@2006"))
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DATABASE", "portpulse")





DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base: Any = declarative_base()


class PredictionLog(Base):
    __tablename__ = "prediction_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    vessel_id = Column(String(20))
    window_day = Column(Integer)
    vessel_count = Column(Integer)
    incoming_teu = Column(Integer)
    total_capacity_teu = Column(Integer)
    utilization_ratio = Column(Float)
    predicted_risk_level = Column(String(10))
    predicted_wait_hours = Column(Float)
    actual_wait_hours = Column(Float, nullable=True)
    actual_risk_level = Column(String(10), nullable=True)
    model_version = Column(String(20))
    origin_lat = Column(Float, nullable=True)
    origin_lon = Column(Float, nullable=True)
    origin_port = Column(String(128), nullable=True)
    dest_lat = Column(Float, nullable=True)
    dest_lon = Column(Float, nullable=True)
    dest_port = Column(String(128), nullable=True)
    weather_delay_hours = Column(Float, nullable=True)
    weather_severity = Column(String(20), nullable=True)
    predicted_demurrage_cost_usd = Column(Float, nullable=True)
    predicted_moves_per_hour = Column(Float, nullable=True)
    is_anomalous = Column(Integer, nullable=True)
    ml_allocation_used = Column(Integer, nullable=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> bool:
    """Ensure database connection and metadata tables exist."""
    try:
        import pymysql

        admin_conn = pymysql.connect(
            host=DB_HOST,
            port=int(DB_PORT),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
        )
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
        admin_conn.close()

        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        Base.metadata.create_all(bind=engine)
        return True
    except Exception as err:
        logger.warning("MySQL database initialization skipped: %s", err)
        return False


def check_connection() -> bool:
    return init_db()


# Initialize database schema on module import if DB is accessible
init_db()



