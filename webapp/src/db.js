const path = require("path");
const { Pool } = require("pg");

require("dotenv").config({ path: path.resolve(__dirname, "..", "..", ".env") });

// POSTGRES_SSLMODE=require (p.ej. Neon/Supabase en producción) activa TLS;
// en local (Postgres nativo) se deja sin definir y no se usa SSL.
const pool = new Pool({
  host: process.env.POSTGRES_HOST || "localhost",
  port: Number(process.env.POSTGRES_PORT || 5432),
  database: process.env.POSTGRES_DB || "agroflow",
  user: process.env.POSTGRES_USER || "agroflow",
  password: process.env.POSTGRES_PASSWORD || "agroflow_dev",
  ssl: process.env.POSTGRES_SSLMODE === "require" ? { rejectUnauthorized: false } : undefined,
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 8000,
});

pool.on("error", (err) => {
  console.error("[db] error inesperado en cliente inactivo", err);
});

module.exports = { pool };
