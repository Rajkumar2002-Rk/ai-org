import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Depends, HTTPException, status

# Read the database URL from environment variables
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='DATABASE_URL environment variable is not set'
    )

# Create the async SQLAlchemy engine
try:
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
except Exception as e:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='Failed to connect to the database'
    ) from e

# Create a configured "Session" class
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Create a Base class for declarative class definitions
Base = declarative_base()

# Dependency to get the database session
async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred"
            ) from e
