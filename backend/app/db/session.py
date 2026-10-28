import logging
import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Engine initialization options based on DB dialect
engine_kwargs = {
    "pool_pre_ping": settings.DB_POOL_PRE_PING,
}

if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
        }
    )

engine: Engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connectivity() -> tuple[bool, float, str | None]:
    """Execute a lightweight probe ('SELECT 1') against the database.

    Returns:
        tuple[bool, float, str | None]: (is_healthy, latency_ms, error_message)
    """
    start_time = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return True, latency_ms, None
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        from app.core.logging import redact_sensitive_data
        sanitized = redact_sensitive_data(str(exc))
        logger.warning("Database connectivity check failed: %s", sanitized)
        return False, latency_ms, sanitized


def dispose_engine() -> None:
    """Safely dispose of the database connection pool on shutdown."""
    logger.info("Disposing database connection pool...")
    engine.dispose()
