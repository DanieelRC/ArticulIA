"""Conexión a PostgreSQL y aplicación del esquema."""

from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from articulia.config import get_settings

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(autocommit: bool = False) -> psycopg.Connection:
    """Abre una conexión con el tipo `vector` registrado."""
    conn = psycopg.connect(get_settings().database_url, autocommit=autocommit)
    # register_vector necesita que el tipo exista; en una base nueva aún no está.
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if not autocommit:
        conn.commit()
    register_vector(conn)
    return conn


def apply_schema(conn: psycopg.Connection) -> None:
    """Crea extensiones, tablas e índices si no existen."""
    conn.execute(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
