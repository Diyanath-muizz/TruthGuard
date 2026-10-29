"""
database/initialization.py
──────────────────────────
Database bootstrap utilities for TruthGuard.

Usage::

    from database.initialization import initialize_database, get_db

    # Called once at application startup
    initialize_database()

    # Session context manager for normal use
    with get_db() as session:
        ...
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from database.models import Base

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Engine creation
# ─────────────────────────────────────────────────────────────────────────────

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine() -> Engine:
    """
    Create and configure the SQLAlchemy engine.

    SQLite-specific tweaks applied:
    - ``PRAGMA journal_mode=WAL``  – better concurrent read performance
    - ``PRAGMA foreign_keys=ON``   – enforce FK constraints at the DB level
    - ``check_same_thread=False``  – required for multi-threaded Streamlit use
    """
    db_url = settings.sqlite_url

    # Ensure the parent directory exists
    db_path = Path(settings.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        db_url,
        connect_args=connect_args,
        echo=(settings.log_level == "DEBUG"),
        future=True,
    )

    # Apply SQLite PRAGMAs on every new connection
    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    logger.debug("SQLAlchemy engine created: %s", db_url)
    return engine


def get_engine() -> Engine:
    """Return (and lazily create) the module-level SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    """Return (and lazily create) the module-level session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _SessionLocal


# ─────────────────────────────────────────────────────────────────────────────
# Session context manager
# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional SQLAlchemy session.

    Usage::

        with get_db() as session:
            doc = session.get(Document, 1)

    The session is committed on clean exit and rolled back on any exception.
    It is always closed when the ``with`` block exits.
    """
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# Database initialisation
# ─────────────────────────────────────────────────────────────────────────────


def _tables_exist(engine: Engine) -> bool:
    """Return True if at least one application table already exists."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    required = set(Base.metadata.tables.keys())
    return bool(existing & required)


def initialize_database(force_recreate: bool = False) -> None:
    """
    Create all tables defined in ``database.models``.

    Behaviour:
    - On first run (tables absent) – creates all tables.
    - On restart (tables already exist) – does nothing unless
      ``force_recreate=True``, in which case **all data is dropped** and
      tables are recreated.  Only use that flag in tests.

    Args:
        force_recreate: Drop all tables before creating them.  Destructive –
            use only in tests or during development.
    """
    engine = get_engine()

    if force_recreate:
        logger.warning(
            "force_recreate=True – dropping all TruthGuard tables.  "
            "This is destructive and should only happen in tests."
        )
        Base.metadata.drop_all(bind=engine)
        logger.info("All tables dropped.")

    if _tables_exist(engine) and not force_recreate:
        logger.info(
            "Database tables already exist at %s – skipping creation.",
            settings.sqlite_db_path,
        )
        _log_table_summary(engine)
        return

    logger.info("Creating TruthGuard database tables at %s …", settings.sqlite_db_path)
    Base.metadata.create_all(bind=engine)
    logger.info(
        "Successfully created %d table(s): %s",
        len(Base.metadata.tables),
        ", ".join(sorted(Base.metadata.tables.keys())),
    )

    # Seed any static/reference data here if needed in the future
    _seed_initial_data(engine)


def _seed_initial_data(engine: Engine) -> None:
    """
    Insert any required seed data after a fresh table creation.

    Currently this is a no-op; the hook exists so future seeds can be added
    without modifying ``initialize_database`` itself.
    """
    logger.debug("No seed data to insert.")


def _log_table_summary(engine: Engine) -> None:
    """Log row counts for each application table (debug aid)."""
    if logger.isEnabledFor(logging.DEBUG):
        inspector = inspect(engine)
        with engine.connect() as conn:
            for table_name in sorted(inspector.get_table_names()):
                if table_name in Base.metadata.tables:
                    try:
                        result = conn.execute(
                            text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
                        )
                        count = result.scalar()
                        logger.debug("  %-35s %d rows", table_name, count)
                    except Exception as exc:
                        logger.debug("  %-35s <error: %s>", table_name, exc)
