const path = require("path");
const express = require("express");
const apiRouter = require("./src/routes");
const { pool } = require("./src/db");

const app = express();
// Render (y la mayoría de plataformas de hosting) inyecta PORT y exige
// que el servidor escuche justo ahí; WEBAPP_PORT es solo para correrlo
// en un puerto fijo en local si 3000 ya está ocupado.
const PORT = process.env.PORT || process.env.WEBAPP_PORT || 3000;

app.use(express.static(path.join(__dirname, "public")));
app.use("/api", apiRouter);

app.use((err, _req, res, _next) => {
  console.error("[api] error:", err.message);
  res.status(500).json({ error: "Error consultando la base de datos", detalle: err.message });
});

app.listen(PORT, async () => {
  try {
    await pool.query("SELECT 1");
    console.log(`AgroFlow-CO web escuchando en http://localhost:${PORT} (PostgreSQL OK)`);
  } catch (err) {
    console.error(`AgroFlow-CO web escuchando en http://localhost:${PORT}, pero PostgreSQL no responde:`, err.message);
  }
});
