"""Orquestación extracción -> raw -> transformación -> carga (RF-01 a RF-09).

Cada corrida:
1. Llama la operación SOAP real (sin inventar datos).
2. Guarda la respuesta cruda en `data/raw/` (RF-04), incluso si quedó
   incompleta por un corte de conexión del servidor SIPSA.
3. Normaliza y valida con pandas (RF-05/RF-06).
4. Hace upsert en PostgreSQL por `natural_key` para evitar duplicados
   (RF-07/RF-08/RF-09).
5. Registra la corrida en `sipsa_extraction_runs` para trazabilidad.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .soap_raw import SipsaSoapError, call_streaming
from .transform import SOURCE_SPECS, normalize_records

logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def _save_raw(operation: str, rows: list[dict], complete: bool) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "complete" if complete else "partial"
    path = RAW_DIR / f"{operation}_{ts}_{suffix}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("pipeline.save_raw path=%s rows=%d", path, len(rows))
    return str(path)


def run_source(
    operation: str,
    *,
    max_rows: int | None = None,
    persist: bool = True,
    store_raw_payload: bool = True,
) -> dict:
    """Ejecuta el pipeline completo para una operación SIPSA.

    `max_rows` sólo debe usarse en desarrollo/pruebas para acotar el
    tiempo de descarga: corta la conexión de forma deliberada tras N
    filas y por eso la corrida queda marcada como incompleta.
    `persist=False` permite probar extracción+transformación sin tocar
    la base de datos (p.ej. si Postgres no está disponible).
    `store_raw_payload=False` omite guardar el registro crudo en la
    columna `raw_payload` (queda NULL): pensado para la copia "liviana"
    en la nube que alimenta la web pública, donde ese JSON por fila es
    el principal responsable del tamaño en disco y no hace falta (la
    copia local completa, con todo el crudo, sigue intacta).
    """
    if operation not in SOURCE_SPECS:
        raise ValueError(f"Operación no soportada: {operation}. Usar una de {list(SOURCE_SPECS)}")

    started_at = datetime.now(timezone.utc)
    status = "failed"
    error_message = None
    rows_received = 0
    rows_loaded = 0
    raw_path = None

    try:
        result = call_streaming(operation, max_rows=max_rows)
        rows_received = len(result.rows)
        raw_path = _save_raw(operation, result.rows, result.complete)

        df = normalize_records(result.rows, operation)
        rows_valid = len(df)

        if persist:
            raw_by_key = None
            if store_raw_payload:
                # `df.index` conserva la posición original de cada fila
                # dentro de `result.rows` (validate() sólo descarta filas,
                # no reindexa), así que se puede recuperar el crudo exacto
                # de cada registro.
                raw_by_key = {
                    df.loc[idx, "natural_key"]: result.rows[idx]
                    for idx in df.index
                }
            rows_loaded = db.upsert_observations(df.to_dict("records"), raw_by_key)
        else:
            rows_loaded = 0

        status = "success" if result.complete else "partial"
        logger.info(
            "pipeline.run_source operation=%s status=%s received=%d valid=%d loaded=%d",
            operation, status, rows_received, rows_valid, rows_loaded,
        )
    except SipsaSoapError as exc:
        status = "failed"
        error_message = str(exc)
        logger.error("pipeline.run_source operation=%s error=%s", operation, exc)
    finally:
        finished_at = datetime.now(timezone.utc)
        run_record = {
            "source_system": operation,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "rows_received": rows_received,
            "rows_loaded": rows_loaded,
            "raw_file_path": raw_path,
            "error_message": error_message,
        }
        if persist:
            try:
                db.log_extraction_run(run_record)
            except Exception as log_exc:  # no ocultar el resultado real por un fallo al loguear
                logger.error("pipeline.log_extraction_run error=%s", log_exc)

    return run_record


def run_all(
    *, max_rows: int | None = None, persist: bool = True, store_raw_payload: bool = True
) -> list[dict]:
    return [
        run_source(op, max_rows=max_rows, persist=persist, store_raw_payload=store_raw_payload)
        for op in SOURCE_SPECS
    ]
