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

# Determine environment to control SQL echo. Only enable SQL echo outside production.
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production').lower()
SQL_ECHO = ENVIRONMENT not in ('production', 'prod')

# Create the SQLAlchemy engine
try:
    engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO, future=True)
except Exception as e:
    raise RuntimeError(f"Failed to create the database engine: {e}")

# Create a configured "Session" class
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

# Create a base class for declarative class definitions
Base = declarative_base()

# Dependency to get the database session
async def get_db():
    try:
        async with async_session() as session:
            yield session
    except Exception as e:
        logger.exception("Database operation failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
