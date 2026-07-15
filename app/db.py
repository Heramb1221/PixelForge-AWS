"""
app/db.py
---------
Thin wrapper around a psycopg2 threaded connection pool. Kept deliberately
free of an ORM: the schema is small and stable, and raw parameterized SQL
keeps the query plan and behavior fully transparent for a capstone review.
"""
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

_pool = None


def init_pool(app_config):
    global _pool
    if _pool is not None:
        return
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=app_config.DB_POOL_MIN_CONN,
        maxconn=app_config.DB_POOL_MAX_CONN,
        host=app_config.DB_HOST,
        port=app_config.DB_PORT,
        dbname=app_config.DB_NAME,
        user=app_config.DB_USER,
        password=app_config.DB_PASSWORD,
        sslmode=app_config.DB_SSLMODE,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    logger.info("Database connection pool initialized (min=%s, max=%s)",
                app_config.DB_POOL_MIN_CONN, app_config.DB_POOL_MAX_CONN)


@contextmanager
def get_conn():
    """Borrow a connection from the pool; guarantees it's returned."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call init_pool() first.")
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(commit=False):
    """Borrow a connection and yield a cursor. Commits/rolls back automatically."""
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def close_pool():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed.")
