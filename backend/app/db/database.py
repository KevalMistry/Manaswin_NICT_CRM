from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import database_url

db_engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(
    bind=db_engine,
    autocommit=False,
    autoflush=False,
)

database_connected = False

try:
    with db_engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    database_connected = True
    print("Connected to database successfully.")

except SQLAlchemyError as error:
    print(f"Error connecting to database: {error}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()