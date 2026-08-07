from psycopg2 import pool as pg_pool
from psycopg2.extras import Json
import os
from dotenv import load_dotenv
from app.utils import normalizar_nome

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não está definida")

db_pool = pg_pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=DATABASE_URL,
    sslmode="require",
)

def get_conn():
    return db_pool.getconn()

def put_conn(conn):
    db_pool.putconn(conn)

def init_db():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ibge_cache (
                    id   TEXT PRIMARY KEY,
                    payload     JSONB NOT NULL,
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS municipio_coordenadas (
                    nome_municipio  TEXT NOT NULL,
                    uf              TEXT NOT NULL,
                    latitude        DOUBLE PRECISION NOT NULL,
                    longitude       DOUBLE PRECISION NOT NULL,
                    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (nome_municipio, uf)
                );
            """)
    finally:
        put_conn(conn)

def get_data(key: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM ibge_cache WHERE id = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        put_conn(conn)

def update_data(key: str, payload) -> None:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ibge_cache (id, payload, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (id)
                DO UPDATE SET payload = EXCLUDED.payload, updated_at = now();
                """,
                (key, Json(payload)),
            )
    finally:
        put_conn(conn)

def get_coordenadas(nome_municipio: str, uf: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT latitude, longitude FROM municipio_coordenadas WHERE nome_municipio = %s AND uf = %s",
                (normalizar_nome(nome_municipio), normalizar_nome(uf)),
            )
            row = cur.fetchone()
            return (row[0], row[1]) if row else None
    finally:
        put_conn(conn)

def salvar_coordenadas(nome_municipio: str, uf: str, latitude: float, longitude: float) -> None:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO municipio_coordenadas (nome_municipio, uf, latitude, longitude, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (nome_municipio, uf)
                DO UPDATE SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, updated_at = now();
                """,
                (normalizar_nome(nome_municipio), normalizar_nome(uf), latitude, longitude),
            )
    finally:
        put_conn(conn)