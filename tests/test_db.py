from collections.abc import Iterator

import psycopg
import pytest

from articulia.config import get_settings


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    try:
        c = psycopg.connect(get_settings().database_url, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible; corre `docker compose up -d`")
    yield c
    c.close()


def test_extension_vector_habilitada(conn: psycopg.Connection) -> None:
    row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert row is not None, "La extensión vector no está habilitada"


def test_tipo_vector_funciona(conn: psycopg.Connection) -> None:
    row = conn.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector").fetchone()
    assert row is not None
    assert row[0] == pytest.approx(1.0)
