# db/init_db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ Missing DATABASE_URL environment variable.")

# Create the async engine (PostgreSQL)
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Base class for all models
Base = declarative_base()

# Session factory
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Startup helper
async def init_db():
    """Creates all tables on startup"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables ready.")
