import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi import Depends, HTTPException

logger = logging.getLogger(__name__)

# Read the database URL from the environment variable
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Check if DATABASE_URL is empty
if DATABASE_URL == "":
    raise ValueError("DATABASE_URL environment variable is set but is empty.")

# Validate the DATABASE_URL format
if not DATABASE_URL.startswith(('postgresql+asyncpg://', 'mysql+aiomysql://')):
    raise ValueError("DATABASE_URL environment variable is set but invalid.")

# Determine environment (informational only).
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production').lower()

# SQL echo requires an explicit opt-in to avoid accidentally logging sensitive
# query parameters/values. It is enabled ONLY when SQL_ECHO is explicitly set to
# a truthy value AND the environment is not a production environment.
def _is_truthy(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

_SQL_ECHO_OPT_IN = _is_truthy(os.getenv('SQL_ECHO', 'false'))
SQL_ECHO = _SQL_ECHO_OPT_IN and ENVIRONMENT not in ('production', 'prod')

if _SQL_ECHO_OPT_IN and not SQL_ECHO:
    logger.warning("SQL_ECHO opt-in ignored because ENVIRONMENT is production.")

# Create the SQLAlchemy engine
try:
    engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO, future=True)
except Exception as e:
    raise RuntimeError(f"Failed to create the database engine: {e}")

# Create a configured "Session" class
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Changed to False for better performance
    autoflush=False,
    autocommit=False
)

# Create a base class for declarative class definitions
Base = declarative_base()

# Dependency to get the database session.
# NOTE: no broad try/except around `yield` — FastAPI runs the request inside the
# yield, so wrapping it and re-raising as HTTPException(500) would swallow the
# request's own HTTPException(401/404/422) into a 500. Let framework exceptions
# propagate unchanged; the session context manager handles rollback/close.
async def get_db():
    try:
        async with async_session() as session:
            yield session
    except Exception as e:
        logger.error(f"Failed to create a database session: {e}")
        raise HTTPException(status_code=500, detail="Database session creation failed.")
