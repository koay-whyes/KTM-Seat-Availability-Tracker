from __future__ import annotations

import importlib
import os
from typing import Any, Optional


def get_database_connection() -> Optional[Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None

    try:
        psycopg2 = importlib.import_module("psycopg2")

        try:
            return psycopg2.connect(database_url, sslmode="require")
        except Exception:
            return psycopg2.connect(database_url)
    except Exception as e:
        print(f"Postgres connection unavailable: {e}")
        return None


def ensure_snapshot_table(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_snapshots (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                user_id BIGINT,
                chat_id TEXT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                travel_date TEXT NOT NULL,
                selected_services TEXT[],
                train_data JSONB NOT NULL,
                previous_data JSONB,
                source TEXT NOT NULL DEFAULT 'selenium'
            )
            """
        )
    connection.commit()


def save_scrape_snapshot(connection: Any, context_data: dict[str, Any], train_data: list[dict[str, Any]], previous_data: Optional[list[dict[str, Any]]], selected_services: Optional[list[str]]) -> None:
    if connection is None:
        return

    try:
        extras = importlib.import_module("psycopg2.extras")
        Json = extras.Json

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO scrape_snapshots (
                    user_id,
                    chat_id,
                    origin,
                    destination,
                    travel_date,
                    selected_services,
                    train_data,
                    previous_data,
                    source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    context_data.get("user_id"),
                    str(context_data.get("chat_id") or ""),
                    context_data.get("origin"),
                    context_data.get("dest"),
                    context_data.get("date"),
                    selected_services or None,
                    Json(train_data),
                    Json(previous_data) if previous_data is not None else None,
                    "selenium",
                ),
            )

        connection.commit()
    except Exception as e:
        print(f"Failed to save scrape snapshot: {e}")
