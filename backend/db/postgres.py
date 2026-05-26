import os
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sales_db")
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def get_schema_info(engine: Engine) -> dict:
    """Return full schema as a structured dict."""
    inspector = inspect(engine)
    tables = {}
    for table_name in inspector.get_table_names():
        columns = [
            {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
            }
            for col in inspector.get_columns(table_name)
        ]
        fks = [
            {
                "constrained_columns": fk["constrained_columns"],
                "referred_table": fk["referred_table"],
                "referred_columns": fk["referred_columns"],
            }
            for fk in inspector.get_foreign_keys(table_name)
        ]
        tables[table_name] = {"columns": columns, "foreign_keys": fks}
    return tables
