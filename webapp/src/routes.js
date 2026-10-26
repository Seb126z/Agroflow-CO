// Capa de solo lectura sobre PostgreSQL. Ninguna ruta aquí extrae datos
// de SIPSA ni los transforma: eso lo hace exclusivamente el pipeline de
// Python (src/agroflow/*). Esta API solo arma consultas SQL parametrizadas
// (sin concatenar texto del usuario) sobre las tablas/vistas ya cargadas.
const express = require("express");
const { pool } = require("./db");

const router = express.Router();

// Filtros contra sipsa_price_observations (la tabla base, no una vista).
// Importante: v_sipsa_variacion_mensual calcula LAG() OVER() sobre TODO
// el histórico antes de que cualquier WHERE externo pueda aplicarse, así
// que filtrar a través de esa vista es lentísimo (recorre las 775k filas
// completas en cada consulta). Estas dos rutas sí tienen índices sobre
// product/city/observation_date, así que filtran primero y agregan
// después — mucho más rápido.
function buildFilters({ producto, ciudad, mercado, departamento, fuente, desde, hasta }) {
  const clauses = [];
  const params = [];

  const add = (sql, value) => {
    params.push(value);
    clauses.push(sql.replace("?", `$${params.length}`));
  };

  if (producto) add("product ILIKE ?", `%${producto}%`);
  if (ciudad) add("city ILIKE ?", `%${ciudad}%`);
  if (mercado) add("market ILIKE ?", `%${mercado}%`);
  if (departamento) add("department ILIKE ?", `%${departamento}%`);
  if (fuente) add("source_system = ?", fuente);
  if (desde) add("observation_date >= ?", desde);
  if (hasta) add("observation_date <= ?", hasta);

  return { where: clauses.length ? `WHERE ${clauses.join(" AND ")}` : "", params };
}

// GET /api/meta/productos?q=papa
router.get("/meta/productos", async (req, res, next) => {
  try {
    const q = (req.query.q || "").trim();
    const { rows } = await pool.query(
      `SELECT DISTINCT product FROM sipsa_price_observations
       WHERE product ILIKE $1
       ORDER BY product
       LIMIT 50`,
      [`%${q}%`]
    );
    res.json(rows.map((r) => r.product));
  } catch (err) {
    next(err);
  }
});

// GET /api/meta/ciudades?q=bog
router.get("/meta/ciudades", async (req, res, next) => {
  try {
    const q = (req.query.q || "").trim();
    const { rows } = await pool.query(
      `SELECT DISTINCT city FROM sipsa_price_observations
       WHERE city IS NOT NULL AND city ILIKE $1
       ORDER BY city
       LIMIT 50`,
      [`%${q}%`]
    );
    res.json(rows.map((r) => r.city));
  } catch (err) {
    next(err);
  }
});

// GET /api/meta/fuentes
router.get("/meta/fuentes", async (_req, res, next) => {
  try {
    const { rows } = await pool.query(
      `SELECT DISTINCT source_system FROM sipsa_price_observations ORDER BY source_system`
    );
    res.json(rows.map((r) => r.source_system));
  } catch (err) {
    next(err);
  }
});

// GET /api/resumen?producto=&ciudad=&mercado=&departamento=&fuente=&desde=&hasta=
// Sin filtros devuelve los totales globales; con filtros, los KPIs
// reaccionan igual que las tarjetas del dashboard de Power BI.
router.get("/resumen", async (req, res, next) => {
  try {
    const { where, params } = buildFilters(req.query);
    const { rows } = await pool.query(
      `SELECT
         COUNT(*)::int AS total_observaciones,
         COUNT(DISTINCT product)::int AS total_productos,
         COUNT(DISTINCT city)::int AS total_ciudades,
         AVG(average_price) AS precio_promedio,
         MIN(observation_date) AS fecha_minima,
         MAX(observation_date) AS fecha_maxima
       FROM sipsa_price_observations
       ${where}`,
      params
    );
    const { rows: runRows } = await pool.query(`
      SELECT source_system, finished_at, status, rows_loaded
      FROM sipsa_extraction_runs
      ORDER BY finished_at DESC NULLS LAST
      LIMIT 1
    `);
    res.json({ ...rows[0], ultima_corrida: runRows[0] || null });
  } catch (err) {
    next(err);
  }
});

// GET /api/precios/serie?producto=&ciudad=&mercado=&departamento=&fuente=&desde=&hasta=
// Serie mensual (precio_promedio, min, max, variacion_pct) para graficar evolución.
router.get("/precios/serie", async (req, res, next) => {
  try {
    const { where, params } = buildFilters(req.query);
    const { rows } = await pool.query(
      `SELECT date_trunc('month', observation_date)::date AS mes,
              source_system, product, market, city,
              AVG(average_price) AS precio_promedio,
              MIN(min_price) AS precio_minimo,
              MAX(max_price) AS precio_maximo,
              COUNT(*)::int AS num_observaciones
       FROM sipsa_price_observations
       ${where}
       GROUP BY date_trunc('month', observation_date), source_system, product, market, city
       ORDER BY mes
       LIMIT 5000`,
      params
    );
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

// GET /api/precios/por-ciudad?producto=&desde=&hasta=
router.get("/precios/por-ciudad", async (req, res, next) => {
  try {
    const { where, params } = buildFilters(req.query);
    const extra = where ? `${where} AND city IS NOT NULL` : "WHERE city IS NOT NULL";
    const { rows } = await pool.query(
      `SELECT city, AVG(average_price) AS precio_promedio, COUNT(*)::int AS num_observaciones
       FROM sipsa_price_observations
       ${extra}
       GROUP BY city
       ORDER BY precio_promedio DESC
       LIMIT 30`,
      params
    );
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

// GET /api/precios/por-departamento?producto=&desde=&hasta=
router.get("/precios/por-departamento", async (req, res, next) => {
  try {
    const { where, params } = buildFilters(req.query);
    const extra = where ? `${where} AND department IS NOT NULL` : "WHERE department IS NOT NULL";
    const { rows } = await pool.query(
      `SELECT department, AVG(average_price) AS precio_promedio, COUNT(*)::int AS num_observaciones
       FROM sipsa_price_observations
       ${extra}
       GROUP BY department
       ORDER BY precio_promedio DESC
       LIMIT 30`,
      params
    );
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

// GET /api/precios/tabla?producto=&ciudad=&...
// Detalle por producto/mercado con variación % mes a mes, equivalente a la
// tabla del dashboard de Power BI. Filtra y agrega PRIMERO (sobre la tabla
// base, con índices) y solo corre LAG() OVER() sobre ese resultado ya
// reducido — no sobre las 775k filas completas como haría la vista.
router.get("/precios/tabla", async (req, res, next) => {
  try {
    const { where, params } = buildFilters(req.query);
    const { rows } = await pool.query(
      `WITH filtrado AS (
         SELECT date_trunc('month', observation_date)::date AS mes,
                source_system, product, market,
                AVG(average_price) AS precio_promedio,
                COUNT(*)::int AS num_observaciones
         FROM sipsa_price_observations
         ${where}
         GROUP BY date_trunc('month', observation_date), source_system, product, market
       ),
       con_variacion AS (
         SELECT *,
                ROUND(
                  100.0 * (precio_promedio - LAG(precio_promedio) OVER (
                    PARTITION BY source_system, product, market ORDER BY mes
                  )) / NULLIF(LAG(precio_promedio) OVER (
                    PARTITION BY source_system, product, market ORDER BY mes
                  ), 0),
                  2
                ) AS variacion_pct
         FROM filtrado
       )
       SELECT product, market,
              AVG(precio_promedio) AS precio_promedio,
              AVG(variacion_pct) AS variacion_pct_promedio,
              SUM(num_observaciones)::int AS num_observaciones
       FROM con_variacion
       GROUP BY product, market
       ORDER BY product, market
       LIMIT 500`,
      params
    );
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

// GET /api/precios/volatiles?limit=10
router.get("/precios/volatiles", async (req, res, next) => {
  try {
    const limit = Math.min(Number(req.query.limit) || 10, 50);
    const { rows } = await pool.query(
      `SELECT product, market,
              STDDEV(variacion_pct) AS volatilidad_pct,
              AVG(precio_promedio) AS precio_promedio_general,
              COUNT(*)::int AS num_meses
       FROM v_sipsa_variacion_mensual
       WHERE variacion_pct IS NOT NULL
       GROUP BY product, market
       HAVING COUNT(*) >= 3
       ORDER BY volatilidad_pct DESC
       LIMIT $1`,
      [limit]
    );
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
