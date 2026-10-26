"""Métricas analíticas sobre los datos cargados (RF-11/RF-12).

Se apoya en las vistas SQL `v_sipsa_precio_mensual_producto` y
`v_sipsa_variacion_mensual` definidas en sql/001_initial_schema.sql, y
expone helpers en pandas para filtrar por periodo, producto y ubicación
como pide RF-12, pensados para alimentar el futuro dashboard
(Looker Studio) sin tener que repetir la lógica de agregación allí.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from .db import get_engine


def precio_mensual_por_producto(
    product: str | None = None,
    city: str | None = None,
    market: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> pd.DataFrame:
    """Serie mensual de precios por producto/mercado con filtros opcionales."""
    clauses = []
    params: dict = {}
    if product:
        clauses.append("product ILIKE :product")
        params["product"] = f"%{product}%"
    if city:
        clauses.append("city ILIKE :city")
        params["city"] = f"%{city}%"
    if market:
        clauses.append("market ILIKE :market")
        params["market"] = f"%{market}%"
    if desde:
        clauses.append("mes >= :desde")
        params["desde"] = desde
    if hasta:
        clauses.append("mes <= :hasta")
        params["hasta"] = hasta

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = text(f"SELECT * FROM v_sipsa_variacion_mensual {where} ORDER BY mes")
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params=params)


def top_productos_mas_volatiles(limit: int = 10) -> pd.DataFrame:
    """Productos con mayor desviación estándar de variación mensual (%)."""
    query = text(
        """
        SELECT product, market,
               STDDEV(variacion_pct) AS volatilidad_pct,
               AVG(precio_promedio) AS precio_promedio_general,
               COUNT(*) AS num_meses
        FROM v_sipsa_variacion_mensual
        WHERE variacion_pct IS NOT NULL
        GROUP BY product, market
        HAVING COUNT(*) >= 3
        ORDER BY volatilidad_pct DESC
        LIMIT :limit
        """
    )
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


def resumen_por_ciudad(desde: str | None = None) -> pd.DataFrame:
    """Precio promedio actual por ciudad/producto (para comparar ubicaciones)."""
    clauses = ["city IS NOT NULL"]
    params: dict = {}
    if desde:
        clauses.append("observation_date >= :desde")
        params["desde"] = desde
    where = f"WHERE {' AND '.join(clauses)}"
    query = text(
        f"""
        SELECT city, product,
               AVG(average_price) AS precio_promedio,
               MIN(average_price) AS precio_minimo,
               MAX(average_price) AS precio_maximo,
               COUNT(*) AS num_observaciones
        FROM sipsa_price_observations
        {where}
        GROUP BY city, product
        ORDER BY city, product
        """
    )
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params=params)


def export_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False, encoding="utf-8")
