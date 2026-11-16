import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DATABASE_URL
from sqlalchemy import inspect, text

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_options.update(pool_size=5, max_overflow=10)
engine = create_engine(DATABASE_URL, **engine_options)


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(connection, cursor, statement, parameters, context, executemany):
    context._aegis_query_started = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(connection, cursor, statement, parameters, context, executemany):
    started = getattr(context, "_aegis_query_started", None)
    if started is not None:
        from observability import observe, increment

        increment("db.queries")
        observe("db.query", (time.perf_counter() - started) * 1000)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def ensure_schema():
    """Apply additive columns for existing demo databases without destructive migrations."""
    inspector = inspect(engine)
    additions = {
        "conversations": {
            "response_version": "VARCHAR(40) DEFAULT 'response-v1'",
            "prompt_version": "VARCHAR(40) DEFAULT 'prompt-v1'",
            "llm_provider": "VARCHAR(40) DEFAULT 'deterministic'",
            "model_name": "VARCHAR(120) DEFAULT ''",
            "execution_duration_ms": "INTEGER DEFAULT 0",
        },
        "agent_events": {
            "correlation_id": "VARCHAR(80) DEFAULT ''",
        },
        "tickets": {
            "order_id": "VARCHAR(30)",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    ))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
