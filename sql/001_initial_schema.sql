-- Esquema de AgroFlow-CO para datos SIPSA-DANE (precios mayoristas y
-- promedios por ciudad). Ver docs/03-mapeo-campos.md para el origen de
-- cada columna.

CREATE TABLE IF NOT EXISTS sipsa_price_observations (
    id BIGSERIAL PRIMARY KEY,
    natural_key TEXT NOT NULL,
    source_system TEXT NOT NULL,
    period_type TEXT NOT NULL,
    observation_date DATE NOT NULL,
    department TEXT,
    city TEXT,
    market TEXT,
    product TEXT NOT NULL,
    product_group TEXT,
    unit TEXT,
    min_price NUMERIC(14,2),
    max_price NUMERIC(14,2),
    average_price NUMERIC(14,2) NOT NULL,
    source TEXT NOT NULL DEFAULT 'SIPSA-DANE',
    source_updated_at TIMESTAMPTZ,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_payload JSONB,
    CONSTRAINT uq_sipsa_natural_key UNIQUE (natural_key)
);

CREATE INDEX IF NOT EXISTS idx_sipsa_date ON sipsa_price_observations(observation_date);
CREATE INDEX IF NOT EXISTS idx_sipsa_product_date ON sipsa_price_observations(product, observation_date);
CREATE INDEX IF NOT EXISTS idx_sipsa_source_system ON sipsa_price_observations(source_system);
CREATE INDEX IF NOT EXISTS idx_sipsa_city ON sipsa_price_observations(city);
CREATE INDEX IF NOT EXISTS idx_sipsa_market ON sipsa_price_observations(market);

-- Trazabilidad de cada corrida de extracción (RF-04, RF-10 y
-- requisitos no funcionales de trazabilidad/reproducibilidad).
CREATE TABLE IF NOT EXISTS sipsa_extraction_runs (
    id BIGSERIAL PRIMARY KEY,
    source_system TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    rows_received INTEGER,
    rows_loaded INTEGER,
    raw_file_path TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sipsa_runs_source ON sipsa_extraction_runs(source_system, started_at);

-- Vista analítica: promedio mensual por producto y mercado, con
-- variación relativa respecto al mes anterior (RF-11).
CREATE OR REPLACE VIEW v_sipsa_precio_mensual_producto AS
SELECT
    source_system,
    product,
    market,
    city,
    department,
    date_trunc('month', observation_date)::date AS mes,
    AVG(average_price) AS precio_promedio,
    MIN(min_price) AS precio_minimo,
    MAX(max_price) AS precio_maximo,
    COUNT(*) AS num_observaciones
FROM sipsa_price_observations
GROUP BY source_system, product, market, city, department, date_trunc('month', observation_date);

CREATE OR REPLACE VIEW v_sipsa_variacion_mensual AS
SELECT
    *,
    LAG(precio_promedio) OVER (
        PARTITION BY source_system, product, market
        ORDER BY mes
    ) AS precio_promedio_mes_anterior,
    ROUND(
        100.0 * (precio_promedio - LAG(precio_promedio) OVER (
            PARTITION BY source_system, product, market ORDER BY mes
        )) / NULLIF(LAG(precio_promedio) OVER (
            PARTITION BY source_system, product, market ORDER BY mes
        ), 0),
        2
    ) AS variacion_pct
FROM v_sipsa_precio_mensual_producto;
