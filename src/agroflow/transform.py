"""Normalización y validación de los datos crudos de SIPSA-DANE.

Cada operación SOAP devuelve una forma distinta (ver `docs/03-mapeo-campos.md`
para el detalle campo a campo). Aquí se mapean todas a un esquema único
(`sipsa_price_observations`) para poder compararlas y filtrarlas juntas,
tal como pide RF-05/RF-06/RF-12 del documento de requerimientos.

No se inventan columnas que la fuente no entrega: cuando un dato no viene
en la respuesta (p.ej. unidad en `promediosSipsaCiudad`) se deja en NULL.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)

UNIFIED_COLUMNS = [
    "natural_key",
    "source_system",
    "period_type",
    "observation_date",
    "department",
    "city",
    "market",
    "product",
    "product_group",
    "unit",
    "min_price",
    "max_price",
    "average_price",
    "source",
    "source_updated_at",
]


@dataclass(frozen=True)
class SourceSpec:
    operation: str
    period_type: str
    date_field: str
    product_field: str
    market_field: str | None
    department_field: str | None
    city_field: str | None
    group_field: str | None
    min_field: str | None
    max_field: str | None
    avg_field: str
    created_field: str | None
    unit: str | None


SOURCE_SPECS: dict[str, SourceSpec] = {
    "promediosSipsaMesMadr": SourceSpec(
        operation="promediosSipsaMesMadr",
        period_type="mensual",
        date_field="fechaMesIni",
        product_field="artiNombre",
        market_field="fuenNombre",
        department_field=None,
        city_field=None,
        group_field=None,
        min_field="minimoKg",
        max_field="maximoKg",
        avg_field="promedioKg",
        created_field="fechaCreacion",
        unit="kg",
    ),
    "promediosSipsaSemanaMadr": SourceSpec(
        operation="promediosSipsaSemanaMadr",
        period_type="semanal",
        date_field="fechaIni",
        product_field="artiNombre",
        market_field="fuenNombre",
        department_field=None,
        city_field=None,
        group_field=None,
        min_field="minimoKg",
        max_field="maximoKg",
        avg_field="promedioKg",
        created_field="fechaCreacion",
        unit="kg",
    ),
    "promediosSipsaParcial": SourceSpec(
        operation="promediosSipsaParcial",
        period_type="semanal_parcial",
        date_field="enmaFecha",
        product_field="artiNombre",
        market_field="fuenNombre",
        department_field="deptNombre",
        city_field="muniNombre",
        group_field="grupNombre",
        min_field="minimoKg",
        max_field="maximoKg",
        avg_field="promedioKg",
        created_field=None,
        unit="kg",
    ),
    "promediosSipsaCiudad": SourceSpec(
        operation="promediosSipsaCiudad",
        period_type="diario",
        date_field="fechaCaptura",
        product_field="producto",
        market_field=None,
        department_field=None,
        city_field="ciudad",
        group_field=None,
        min_field=None,
        max_field=None,
        avg_field="precioPromedio",
        created_field="fechaCreacion",
        unit=None,
    ),
}


def _natural_key(row: dict) -> str:
    parts = [
        str(row.get("source_system", "")),
        str(row.get("observation_date", "")),
        str(row.get("department", "")),
        str(row.get("city", "")),
        str(row.get("market", "")),
        str(row.get("product", "")),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest


def normalize_records(records: list[dict], operation: str) -> pd.DataFrame:
    """Convierte los dicts crudos de una operación SIPSA al esquema unificado."""
    spec = SOURCE_SPECS.get(operation)
    if spec is None:
        raise ValueError(f"Operación sin mapeo definido: {operation}")

    if not records:
        return pd.DataFrame(columns=UNIFIED_COLUMNS)

    df = pd.DataFrame(records)

    def col(name: str | None) -> pd.Series:
        # Algunos registros omiten campos opcionales en el XML cuando
        # vienen nulos (JAXB no serializa el elemento); se completan con
        # NaN en vez de fallar o inventar un valor.
        if name is None or name not in df.columns:
            return pd.Series(None, index=df.index)
        return df[name]

    out = pd.DataFrame(index=df.index)
    out["source_system"] = spec.operation
    out["period_type"] = spec.period_type
    out["observation_date"] = pd.to_datetime(col(spec.date_field), errors="coerce", utc=False)
    out["department"] = col(spec.department_field)
    out["city"] = col(spec.city_field)
    out["market"] = col(spec.market_field)
    out["product"] = col(spec.product_field)
    out["product_group"] = col(spec.group_field)
    out["unit"] = spec.unit
    out["min_price"] = pd.to_numeric(col(spec.min_field), errors="coerce")
    out["max_price"] = pd.to_numeric(col(spec.max_field), errors="coerce")
    out["average_price"] = pd.to_numeric(col(spec.avg_field), errors="coerce")
    out["source"] = "SIPSA-DANE"
    out["source_updated_at"] = pd.to_datetime(col(spec.created_field), errors="coerce", utc=False)

    out = validate(out)

    out["natural_key"] = out.apply(
        lambda r: _natural_key(
            {
                "source_system": r["source_system"],
                "observation_date": r["observation_date"],
                "department": r["department"],
                "city": r["city"],
                "market": r["market"],
                "product": r["product"],
            }
        ),
        axis=1,
    )
    # Mejor esfuerzo: reemplaza NaN por None en columnas mixtas (dtype
    # object). No alcanza para una columna que para esta fuente es NaN
    # en TODAS las filas (p.ej. city en promediosSipsaMesMadr): pandas
    # la deja en dtype float64, que no puede contener None de Python, y
    # lo vuelve a convertir en NaN silenciosamente. El saneo real y
    # definitivo (que sí cubre ese caso) está en
    # db.upsert_observations._nan_to_none, justo antes de escribir a la
    # base — ahí ya son dicts de Python sueltos de cualquier dtype.
    out = out.where(pd.notnull(out), None)
    return out[UNIFIED_COLUMNS]


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """RF-06: valida fechas y precios. Las filas inválidas se descartan y
    se registran en el log en vez de intentar adivinar un valor."""
    n0 = len(df)

    bad_date = df["observation_date"].isna()
    bad_price = df["average_price"].isna() | (df["average_price"] < 0)
    bad_product = df["product"].isna() | (df["product"].astype(str).str.strip() == "")

    if "min_price" in df and "max_price" in df:
        has_both = df["min_price"].notna() & df["max_price"].notna()
        bad_range = has_both & (df["min_price"] > df["max_price"])
    else:
        bad_range = pd.Series(False, index=df.index)

    bad = bad_date | bad_price | bad_product | bad_range
    if bad.any():
        logger.warning(
            "validate: descartando %d/%d filas inválidas (fecha=%d, precio=%d, producto=%d, rango=%d)",
            int(bad.sum()),
            n0,
            int(bad_date.sum()),
            int(bad_price.sum()),
            int(bad_product.sum()),
            int(bad_range.sum()),
        )
    df = df.loc[~bad].copy()
    df["observation_date"] = df["observation_date"].dt.date
    return df
