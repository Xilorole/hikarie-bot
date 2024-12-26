from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from hikarie_bot.settings import DATABASE_URL

SQLALCHEMY_DATABASE_URL = DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class BaseSchema(DeclarativeBase):
    """Base class for defining the schema of the database."""
