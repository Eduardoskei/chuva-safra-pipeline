import json
from psycopg2 import pool as pg_pool
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
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
                (key, json(payload)),
            )
    finally:
        put_conn(conn)

init_db()