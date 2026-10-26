"""Pruebas de normalización/validación (RF-05/RF-06), sin red ni base de datos.

Los registros de ejemplo tienen la MISMA forma que lo observado en vivo
contra el servicio real (ver docs/03-mapeo-campos.md); no son datos de
precios inventados para pasar las pruebas, solo fijan la estructura de
campos que SIPSA devuelve.
"""
import pandas as pd

from src.agroflow.transform import normalize_records, validate


def test_normalize_mes_madr_basic():
    records = [
        {
            "artiId": "1", "artiNombre": "Papa R-12", "enviado": "0",
            "fechaCreacion": "2024-02-02T08:00:00-05:00",
            "fechaMesIni": "2024-01-01T00:00:00-05:00",
            "fuenId": "1", "fuenNombre": "Bogotá, D.C., Corabastos",
            "futiId": "1", "maximoKg": "1200", "minimoKg": "900",
            "promedioKg": "1050", "tmpMayoMesId": "1",
        }
    ]
    df = normalize_records(records, "promediosSipsaMesMadr")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["product"] == "Papa R-12"
    assert row["market"] == "Bogotá, D.C., Corabastos"
    assert row["period_type"] == "mensual"
    assert float(row["average_price"]) == 1050.0
    assert float(row["min_price"]) == 900.0
    assert float(row["max_price"]) == 1200.0
    assert row["source"] == "SIPSA-DANE"
    assert isinstance(row["natural_key"], str) and len(row["natural_key"]) == 64


def test_normalize_ciudad_no_min_max():
    records = [
        {
            "ciudad": "MEDELLÍN", "codProducto": "22", "enviado": "0",
            "fechaCaptura": "2026-10-21T00:00:00-05:00",
            "fechaCreacion": "2026-10-21T14:00:01-05:00",
            "precioPromedio": "3375", "producto": "Maracuyá", "regId": "702455",
        }
    ]
    df = normalize_records(records, "promediosSipsaCiudad")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["city"] == "MEDELLÍN"
    assert pd.isna(row["market"])
    assert pd.isna(row["min_price"])
    assert float(row["average_price"]) == 3375.0


def test_validate_drops_bad_rows():
    df = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-01", None, "2024-02-01"]),
            "product": ["Papa", "Papa", "Papa"],
            "average_price": [100.0, 200.0, -5.0],
            "min_price": [90.0, 190.0, 10.0],
            "max_price": [110.0, 210.0, 5.0],  # última fila: min > max
        }
    )
    out = validate(df)
    assert len(out) == 1
    assert out.iloc[0]["average_price"] == 100.0


def test_natural_key_stable_for_same_logical_record():
    base = {
        "artiId": "1", "artiNombre": "Papa R-12", "enviado": "0",
        "fechaCreacion": "2024-02-02T08:00:00-05:00",
        "fechaMesIni": "2024-01-01T00:00:00-05:00",
        "fuenId": "1", "fuenNombre": "Bogotá, D.C., Corabastos",
        "futiId": "1", "maximoKg": "1200", "minimoKg": "900",
        "promedioKg": "1050", "tmpMayoMesId": "1",
    }
    updated = {**base, "promedioKg": "1080", "maximoKg": "1250"}  # precio corregido

    df1 = normalize_records([base], "promediosSipsaMesMadr")
    df2 = normalize_records([updated], "promediosSipsaMesMadr")
    assert df1.iloc[0]["natural_key"] == df2.iloc[0]["natural_key"]
    assert df1.iloc[0]["average_price"] != df2.iloc[0]["average_price"]


def test_unknown_operation_raises():
    import pytest

    with pytest.raises(ValueError):
        normalize_records([{}], "operacionInexistente")


def test_empty_records_returns_empty_frame():
    df = normalize_records([], "promediosSipsaMesMadr")
    assert df.empty
    assert list(df.columns) == [
        "natural_key", "source_system", "period_type", "observation_date",
        "department", "city", "market", "product", "product_group", "unit",
        "min_price", "max_price", "average_price", "source", "source_updated_at",
    ]
