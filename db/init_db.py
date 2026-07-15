"""
init_db.py
----------
One-shot script that connects to the configured RDS instance and applies
db/schema.sql. Safe to re-run: every statement in schema.sql uses
CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.

Usage:
    python db/init_db.py

Requires the same environment variables as the Flask app
(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD). See .env.example.
"""
import os
import sys
import logging

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_db")


def load_config():
    load_dotenv()
    required = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    return {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "sslmode": os.getenv("DB_SSLMODE", "require"),
    }


def main():
    config = load_config()
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    if not os.path.exists(schema_path):
        logger.error("schema.sql not found at %s", schema_path)
        sys.exit(1)

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    logger.info("Connecting to database %s at %s:%s ...", config["dbname"], config["host"], config["port"])
    try:
        conn = psycopg2.connect(**config)
    except psycopg2.OperationalError as exc:
        logger.error("Could not connect to the database: %s", exc)
        sys.exit(1)

    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        logger.info("Schema applied successfully.")
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to apply schema: %s", exc)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
