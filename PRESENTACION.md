# Guía de presentación — AgroFlow CO

Estructura sugerida para presentar el proyecto, fase por fase, con qué
capturas de pantalla tomar en cada una. Pensada para una presentación de
~30 minutos; ajusta el nivel de detalle según el tiempo que tengas.

> Antes de presentar: abre el link de la web (Render) y el dashboard de
> Power BI Service un par de minutos antes, para que ya estén "despiertos"
> y no haya demora en vivo (ver sección "Problemas comunes" del README).

---

## 0. Introducción (1-2 min)

**Explica:** qué es AgroFlow CO en una frase — un pipeline que automatiza
la obtención, limpieza, almacenamiento y visualización de precios
mayoristas agrícolas reales de Colombia, publicados por el DANE.

**Menciona la arquitectura completa de un vistazo:**
```
SIPSA-DANE (SOAP) → Python (extrae/valida) → PostgreSQL → [Power BI | Web propia]
```

**Captura:** ninguna todavía — esto es solo la introducción oral. Si
quieres un apoyo visual, usa el diagrama de arquitectura de la sección 8.

---

## 1. La fuente de datos real (3 min)

**Explica:** SIPSA (Sistema de Información de Precios y Abastecimiento
del Sector Agropecuario) es el sistema oficial del DANE que reporta
precios mayoristas diarios/semanales/mensuales en centrales de abastos
de todo el país. El servicio es un webservice SOAP antiguo, sin
documentación moderna — hubo que inspeccionarlo en vivo para descubrir
qué operaciones existen realmente.

**Captura:**
- La página oficial de SIPSA-DANE en el navegador (la URL está en
  [docs/02-fuentes.md](docs/02-fuentes.md)).
- La terminal corriendo `python -m src.agroflow.cli inspect-wsdl`,
  mostrando las 6 operaciones reales descubiertas en el WSDL.

---

## 2. Extracción (Python + SOAP) (4 min)

**Explica:** el reto no fue solo "llamar un webservice" — en el camino
aparecieron problemas reales de un servicio de gobierno legado:
- El WSDL anuncia un endpoint HTTP que redirige a HTTPS, y esa
  redirección rompe el POST SOAP (toca apuntar directo al HTTPS real).
- Las operaciones no aceptan filtros: siempre devuelven *todo* el
  histórico disponible (cientos de miles de filas).
- El servidor corta la conexión a mitad de transmisión en respuestas
  grandes — así que el extractor parsea en *streaming* y conserva lo
  recibido en vez de perderlo todo.

**Captura:**
- [src/agroflow/soap_raw.py](src/agroflow/soap_raw.py) abierto en el
  editor (la función `call_streaming`), para mostrar el manejo de
  conexión cortada.
- La terminal corriendo `python -m src.agroflow.cli extract --all`,
  mostrando el log en vivo (filas recibidas, `status=partial` o
  `success`).

---

## 3. Conservar el dato crudo (RF-04) (2 min)

**Explica:** antes de transformar nada, se guarda la respuesta cruda del
servicio tal cual llega — por trazabilidad y para poder reprocesar sin
volver a golpear el servicio de DANE.

**Captura:**
- La carpeta `data/raw/` con varios archivos `.jsonl`.
- El contenido de uno abierto (unas pocas líneas), mostrando el JSON
  crudo por fila.

---

## 4. Transformación y validación (pandas) (4 min)

**Explica:** las 4 fuentes que se usan tienen forma distinta entre sí
(campos diferentes, granularidad diferente — mensual/semanal/diaria) y
se normalizan a un esquema único. Se validan fechas y precios (se
descartan filas inválidas en vez de inventar valores).

**Buena historia para contar aquí:** un bug real que apareció y se
corrigió — campos ausentes en una fuente llegaban como `NaN` de pandas y
terminaban guardados como el texto literal `"NaN"` en vez de quedar
vacíos (contaminaba filtros y promedios). Se encontró porque apareció
una ciudad llamada "NaN" en un filtro, se rastreó hasta la causa (pandas
no puede guardar `None` en una columna 100% vacía) y se corrigió en el
punto exacto donde se escribe a la base — con un `ON CONFLICT` que
además autocorrige datos viejos al reextraer.

**Captura:**
- [src/agroflow/transform.py](src/agroflow/transform.py) — la función
  `normalize_records` y/o `validate`.
- [docs/03-mapeo-campos.md](docs/03-mapeo-campos.md) — la tabla de
  mapeo campo a campo por fuente.

---

## 5. Almacenamiento en PostgreSQL, sin duplicados (RF-07/08/09) (3 min)

**Explica:** PostgreSQL instalado nativo en Windows (se intentó con
Docker primero, pero el equipo no soportaba WSL2 — otra decisión técnica
real tomada en el camino). Como el servicio de SIPSA no da un ID de
negocio estable, se calcula una clave natural (hash de fuente + fecha +
ubicación + producto) para hacer *upsert* y nunca duplicar una
observación.

**Captura:**
- [sql/001_initial_schema.sql](sql/001_initial_schema.sql) abierto,
  mostrando la tabla `sipsa_price_observations` y la columna
  `natural_key UNIQUE`.
- `psql` o pgAdmin mostrando `SELECT count(*) FROM sipsa_price_observations;`
  con el número real de filas cargadas.

---

## 6. Automatización (RF-10) (3 min)

**Explica:** dos capas de automatización:
1. Localmente, un script para Task Scheduler de Windows.
2. En la nube, un workflow de **GitHub Actions** que corre todos los
   días sin depender de que ninguna PC esté prendida — extrae de SIPSA
   y carga directo a una base en PostgreSQL en la nube (Neon).

**Captura:**
- [.github/workflows/sync-cloud-db.yml](.github/workflows/sync-cloud-db.yml)
  abierto.
- La pestaña **Actions** del repo en GitHub, mostrando corridas pasadas
  en verde (✓).

---

## 7. Analítica y métricas (RF-11/12) (2 min)

**Explica:** vistas SQL que calculan promedios mensuales y variación %
mes a mes por producto/mercado, pensadas para alimentar filtros
dinámicos por periodo, producto y ubicación.

**Captura:**
- [sql/001_initial_schema.sql](sql/001_initial_schema.sql) — las vistas
  `v_sipsa_precio_mensual_producto` y `v_sipsa_variacion_mensual`.
- La terminal corriendo `python -m src.agroflow.cli metrics --product papa`.

---

## 8. Visualización — dos caminos (8-10 min, la parte más visual)

**Explica:** se construyeron **dos** capas de visualización sobre la
misma base de datos, para comparar herramientas:

### 8a. Dashboard en Power BI
- Filtros dinámicos: producto, ciudad, rango de fechas, fuente.
- Actualización programada diaria (sin Gateway, porque la base ya vive
  en la nube).

**Captura:** el dashboard completo en Power BI Service, con los filtros
aplicados a un producto específico para mostrar que todo reacciona junto.

### 8b. App web propia (Node.js + Express)
- Capa de solo lectura sobre la misma base — no reextrae nada.
- Diseño propio (blanco con acentos rojos), con buscador, filtros,
  gráficas (Chart.js) y tabla de detalle.
- Desplegada en Render, con redeploy automático en cada `git push`.

**Captura:** la web pública en vivo (la URL de Render), mostrando los
filtros funcionando y al menos 2-3 de las gráficas.

---

## 9. Arquitectura de despliegue en la nube (3 min)

**Explica:** nada depende de que una PC esté prendida. El diagrama:

```
GitHub (código)
   │
   ├─► GitHub Actions (cron diario) ──► Neon PostgreSQL (nube)
   │                                         │
   └─► Render (auto-deploy en push) ──► App web ──consulta──┘
                                              │
                                    Power BI Service (refresh diario) ──┘
```

**Captura:** una captura de cada plataforma activa — Neon (dashboard del
proyecto), GitHub Actions (historial en verde), Render (servicio
"Live").

---

## 10. Las 5 preguntas de negocio (5 min)

> Aquí van tus 5 preguntas específicas del trabajo preliminar —
> complétalas y para cada una indica qué gráfica/filtro la responde.

1. **Pregunta 1:** ______ → respondida con: ______
2. **Pregunta 2:** ______ → respondida con: ______
3. **Pregunta 3:** ______ → respondida con: ______
4. **Pregunta 4:** ______ → respondida con: ______
5. **Pregunta 5:** ______ → respondida con: ______

**Captura:** para cada pregunta, la gráfica/filtro específico que la
responde (puedes reusar las del paso 8).

---

## 11. Cierre (1-2 min)

**Menciona:**
- Todo el código está en GitHub, con [SETUP.md](SETUP.md) para que
  cualquiera lo corra desde cero.
- Los datos son 100% reales (ninguno inventado) — verificados en vivo
  contra el servicio oficial de DANE durante el desarrollo.
- Posibles próximos pasos: más fuentes de SIPSA (insumos,
  abastecimiento), más visuales, app móvil.
