# AgroFlow-CO Web

Capa web de **solo lectura** sobre la base de datos de AgroFlow-CO. No extrae ni
transforma datos de SIPSA — eso lo sigue haciendo exclusivamente el pipeline de
Python (`src/agroflow/`). Esta app solo consulta PostgreSQL (vía `pg`) y muestra
los resultados con filtros dinámicos (producto, ciudad, fecha, fuente), igual que
hace el dashboard de Power BI.

## Arrancar

```powershell
cd webapp
npm install
npm start
```

Abre [http://localhost:3000](http://localhost:3000). Usa las credenciales de
PostgreSQL definidas en el `.env` de la raíz del proyecto (`../.env`); no hace
falta duplicarlas.

## Estructura

- `server.js` — arranca Express, sirve `public/` (frontend) y monta `/api`.
- `src/db.js` — pool de conexión a PostgreSQL (`pg`), lee `.env` de la raíz.
- `src/routes.js` — endpoints de solo lectura, todas las consultas son
  parametrizadas (sin concatenar texto del usuario en SQL).
- `public/` — frontend estático (HTML/CSS/JS + Chart.js vía CDN), sin build step.

## Endpoints

| Ruta | Descripción |
|---|---|
| `GET /api/resumen` | KPIs generales + última corrida del pipeline |
| `GET /api/meta/productos?q=` | Lista de productos (para autocompletar) |
| `GET /api/meta/ciudades?q=` | Lista de ciudades |
| `GET /api/meta/fuentes` | Fuentes SIPSA disponibles |
| `GET /api/precios/serie?producto=&ciudad=&mercado=&departamento=&fuente=&desde=&hasta=` | Serie mensual de precios (para el gráfico de evolución) |
| `GET /api/precios/por-ciudad?...` | Precio promedio agregado por ciudad |
| `GET /api/precios/volatiles?limit=` | Productos con mayor variación % mes a mes |

Todos los filtros de query string son opcionales y combinables.
