import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("STEPWISE_DATABASE_URL", "sqlite:///./stepwise.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        if inspect(engine).has_table("users"):
            user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
            if "role" not in user_columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE users "
                            "ADD COLUMN role VARCHAR NOT NULL DEFAULT 'student'"
                        )
                    )

        if inspect(engine).has_table("conversations"):
            conversation_columns = {column["name"] for column in inspect(engine).get_columns("conversations")}
            migrations = {
                "subject": "VARCHAR NOT NULL DEFAULT 'Uncategorized'",
                "frustration_score": "INTEGER NOT NULL DEFAULT 1",
                "consecutive_loops": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, definition in migrations.items():
                if column not in conversation_columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE conversations ADD COLUMN {column} {definition}"))

        if inspect(engine).has_table("messages"):
            message_columns = {column["name"] for column in inspect(engine).get_columns("messages")}
            if "parent_message_id" not in message_columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE messages "
                            "ADD COLUMN parent_message_id INTEGER"
                        )
                    )

        if inspect(engine).has_table("misconception_logs"):
            misconception_columns = {column["name"] for column in inspect(engine).get_columns("misconception_logs")}
            if "is_sample" not in misconception_columns:
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE misconception_logs ADD COLUMN is_sample BOOLEAN NOT NULL DEFAULT 0")
                    )
