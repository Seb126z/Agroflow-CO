-- Índices de texto para búsquedas por substring (ILIKE '%texto%') rápidas.
-- Sin esto, un filtro como product ILIKE '%papa%' no puede usar los
-- índices btree normales (idx_sipsa_product_date, idx_sipsa_city, etc.)
-- porque el comodín al inicio impide el uso de un árbol B, y termina
-- escaneando la tabla completa (observado: ~28s sobre 775k filas).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_sipsa_product_trgm
    ON sipsa_price_observations USING gin (product gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sipsa_city_trgm
    ON sipsa_price_observations USING gin (city gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sipsa_market_trgm
    ON sipsa_price_observations USING gin (market gin_trgm_ops);
