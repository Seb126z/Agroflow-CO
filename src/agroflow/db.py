"""Conexión a PostgreSQL y utilidades de carga (RF-07/RF-08/RF-09)."""
from __future__ import annotations

import json
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = (
            f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )
        _engine = create_engine(
            url, pool_pre_ping=True, connect_args={"connect_timeout": 10}
        )
    return _engine


def apply_schema(sql_path: str) -> None:
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    engine = get_engine()
    with engine.begin() as conn:
        for statement in filter(None, (s.strip() for s in sql.split(";"))):
            conn.execute(text(statement))
    logger.info("db.apply_schema path=%s", sql_path)


UPSERT_SQL = text(
    """
    INSERT INTO sipsa_price_observations (
        natural_key, source_system, period_type, observation_date,
        department, city, market, product, product_group, unit,
        min_price, max_price, average_price, source, source_updated_at,
        raw_payload
    ) VALUES (
        :natural_key, :source_system, :period_type, :observation_date,
        :department, :city, :market, :product, :product_group, :unit,
        :min_price, :max_price, :average_price, :source, :source_updated_at,
        :raw_payload
    )
    ON CONFLICT (natural_key) DO UPDATE SET
        min_price = EXCLUDED.min_price,
        max_price = EXCLUDED.max_price,
        average_price = EXCLUDED.average_price,
        source_updated_at = EXCLUDED.source_updated_at,
        raw_payload = EXCLUDED.raw_payload,
        loaded_at = NOW()
    """
)


def upsert_observations(rows: list[dict], raw_by_key: dict[str, dict] | None = None) -> int:
    """Inserta/actualiza observaciones evitando duplicados (natural_key único).

    `raw_payload` conserva el registro crudo original (RF-04) junto a la
    fila normalizada, trazable por natural_key.
    """
    if not rows:
        return 0
    engine = get_engine()
    payload = []
    for row in rows:
        raw = raw_by_key.get(row["natural_key"]) if raw_by_key else None
        payload.append({**row, "raw_payload": json.dumps(raw, ensure_ascii=False, default=str) if raw else None})
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, payload)
    logger.info("db.upsert_observations rows=%d", len(payload))
    return len(payload)


RUN_INSERT_SQL = text(
    """
    INSERT INTO sipsa_extraction_runs (
        source_system, started_at, finished_at, status,
        rows_received, rows_loaded, raw_file_path, error_message
    ) VALUES (
        :source_system, :started_at, :finished_at, :status,
        :rows_received, :rows_loaded, :raw_file_path, :error_message
    )
    RETURNING id
    """
)


def log_extraction_run(record: dict) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        run_id = conn.execute(RUN_INSERT_SQL, record).scalar_one()
    return run_id
