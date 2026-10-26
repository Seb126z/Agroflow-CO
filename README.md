# AgroFlow CO

Pipeline de datos SIPSA-DANE (precios mayoristas): extracción real por
SOAP, normalización/validación con pandas, almacenamiento en
PostgreSQL con deduplicación, métricas analíticas y automatización.
Dashboard (Looker Studio) queda para una siguiente etapa, sobre las
vistas/consultas ya expuestas en `src/agroflow/metrics.py`.

Ver `docs/01-plan.md` (plan), `docs/02-fuentes.md` (fuentes oficiales),
`docs/03-mapeo-campos.md` (mapeo de campos y comportamiento real del
servicio) y `docs/AgroFlow-CO-Requerimientos.docx` (requerimientos).

## Stack
Python + `requests`/`lxml` (extracción SOAP en streaming) + `zeep`
(solo para inspeccionar el WSDL) + pandas + SQLAlchemy/psycopg +
**PostgreSQL nativo en Windows** (sin Docker: en este equipo Docker
Desktop no pudo iniciar su motor porque WSL2 no está disponible, así
que se optó por instalar PostgreSQL directamente con el instalador
oficial de EDB). `docker-compose.yml` queda como alternativa documentada
para quien sí tenga Docker funcionando.

## Puesta en marcha (PowerShell, Windows)

### 0) PostgreSQL nativo (una sola vez)

```powershell
winget install --id PostgreSQL.PostgreSQL.17 -e --accept-package-agreements --accept-source-agreements
```

El instalador de EDB es pesado (extrae pgAdmin 4 con sus dependencias
de Python, decenas de miles de archivos pequeños): puede tardar
20-40 minutos según el disco/antivirus, sin que eso signifique que
está colgado. Verifica que terminó con:

```powershell
Get-Service postgresql-x64-17   # Status debe quedar "Running"
```

**Si instalaste en modo silencioso** (`--silent`, como en esta sesión),
el asistente no muestra ningún diálogo y por lo tanto nunca ves la
contraseña del superusuario `postgres` que el instalador generó. Para
fijarla tú mismo (solo la primera vez):

```powershell
# 1) Permitir temporalmente conexiones locales sin contraseña:
#    en C:\Program Files\PostgreSQL\17\data\pg_hba.conf cambia las 3
#    líneas "scram-sha-256" (local, host 127.0.0.1/32, host ::1/128) a "trust"
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command "Restart-Service -Name postgresql-x64-17 -Force"' -Wait

# 2) Fijar contraseña y crear el rol/base de AgroFlow-CO (coinciden con .env.example):
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 -c "ALTER ROLE postgres WITH PASSWORD 'agroflow_dev';"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE ROLE agroflow LOGIN PASSWORD 'agroflow_dev';"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE DATABASE agroflow OWNER agroflow;"

# 3) Revertir pg_hba.conf a "scram-sha-256" y reiniciar el servicio otra vez
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command "Restart-Service -Name postgresql-x64-17 -Force"' -Wait
```

Si instalaste de forma interactiva, el propio asistente te pide esa
contraseña en un diálogo; en ese caso solo necesitas los dos `CREATE`
del paso 2 (con `-U postgres` y la contraseña que elegiste).

(Si usas otro usuario/contraseña/puerto, ajusta `.env` en vez del rol
`agroflow` por defecto.)

### 1) Entorno Python + pipeline

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # si no existe ya

# Inspeccionar el WSDL real (RF-01/RF-02)
python -m src.agroflow.cli inspect-wsdl

# Crear el esquema en PostgreSQL
python -m src.agroflow.cli init-db

# Extraer + normalizar + cargar una fuente, o todas
python -m src.agroflow.cli extract --source promediosSipsaCiudad
python -m src.agroflow.cli extract --all

# Consultar métricas ya cargadas
python -m src.agroflow.cli metrics --product papa
python -m src.agroflow.cli metrics --top-volatiles
python -m src.agroflow.cli metrics --by-city --export data/processed/por_ciudad.csv
```

### Alternativa con Docker (si tu equipo sí lo soporta)
```powershell
docker compose up -d db
python -m src.agroflow.cli init-db
```

### Pruebas
```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
6 pruebas unitarias sobre `transform.py` (normalización, validación,
clave natural estable, operación desconocida). No requieren red ni
base de datos.

## Fuentes de datos (reales, verificadas en esta sesión contra el servicio en producción)

El servicio SOAP de SIPSA (`http://appweb.dane.gov.co:80/sipsaWS/SrvSipsaUpraBeanService?wsdl`)
expone 6 operaciones; el pipeline implementa las 4 de precios
mayoristas (alcance de la v0.1, ver `docs/03-mapeo-campos.md`):

- `promediosSipsaMesMadr` — mensual, por central de abastos.
- `promediosSipsaSemanaMadr` — semanal, por central de abastos.
- `promediosSipsaParcial` — semana en curso, con departamento/municipio/grupo.
- `promediosSipsaCiudad` — boletín diario de precio promedio por ciudad.

Ninguna admite filtros de fecha: siempre devuelven todo el historial
disponible. El cliente (`src/agroflow/soap_raw.py`) llama directamente
al endpoint HTTPS real (el WSDL anuncia HTTP:80, que redirige a
HTTPS:443 y rompe el POST SOAP tras la redirección) y parsea la
respuesta en streaming para no cargar en memoria archivos de decenas
de MB.

**Importante — el servicio del gobierno es lento y, en respuestas muy
grandes, corta la conexión antes de terminar** (se observó en vivo con
`promediosSipsaSemanaMadr` y `promediosSipsaCiudad`: ~65 MB
transferidos y corte a mitad de un registro tras varios minutos). El
pipeline está diseñado para esto: conserva las filas ya recibidas y
marca la corrida como `partial` en `sipsa_extraction_runs` en vez de
perder los datos o fallar por completo. Para la primera carga histórica
completa, conviene ejecutar `extract --all` en un horario de baja carga
y aceptar que puede necesitar más de un intento; `--max-rows N` existe
solo para pruebas rápidas (corta la descarga deliberadamente).

## Esquema de base de datos

`sql/001_initial_schema.sql`:
- `sipsa_price_observations`: tabla unificada de las 4 fuentes, con
  `natural_key` único (hash de fuente+fecha+ubicación+producto) para
  evitar duplicados vía `ON CONFLICT ... DO UPDATE` (RF-09), y
  `raw_payload JSONB` con el registro crudo original (RF-04).
- `sipsa_extraction_runs`: trazabilidad de cada corrida (filas
  recibidas/cargadas, estado, ruta del archivo crudo, error si aplica).
- `v_sipsa_precio_mensual_producto` / `v_sipsa_variacion_mensual`:
  vistas de agregación mensual y variación % mes a mes por
  producto/mercado (RF-11), base para los filtros de `metrics.py`
  (RF-12: por periodo, producto y ubicación).

## Automatización (RF-10)

Dos opciones, ambas ya implementadas:

- **Daemon simple**: `python -m src.agroflow.cli run-forever --interval-hours 24`
  (bucle en primer plano, útil para contenedor/servicio).
- **Task Scheduler de Windows**: `scripts/run_pipeline.ps1` ejecuta
  `extract --all` y deja log en `data/processed/logs/`. Registrar una
  vez con:
  ```powershell
  schtasks /create /tn "AgroFlow-CO Pipeline" /sc DAILY /st 03:00 `
    /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"C:\Users\cnseb\3D Objects\AgroFlow-CO\scripts\run_pipeline.ps1`""
  ```

## Estado / pendientes

- **Pipeline completo verificado en vivo de punta a punta**: Docker
  Desktop no pudo usarse en este equipo (su motor Linux/WSL2 nunca
  arrancó: `wsl --status` falla), así que se instaló PostgreSQL 17
  nativo con winget. Con eso funcionando, se ejecutó `extract` real
  (sin `--no-persist`) para las 4 fuentes contra el servicio de DANE en
  producción: 1500 filas reales por fuente (6000 en total) quedaron
  cargadas en `sipsa_price_observations`, con las 5 corridas
  correspondientes registradas en `sipsa_extraction_runs`. Se confirmó
  además la deduplicación (RF-09): re-extraer `promediosSipsaCiudad`
  actualizó las 1500 filas existentes por `natural_key` en vez de
  duplicarlas. `metrics.py` (`--product`, `--top-volatiles`,
  `--by-city --export`) se probó contra esos datos reales ya cargados.
- Dashboard / Looker Studio: pendiente (explícitamente fuera del
  alcance de esta primera versión según
  `docs/AgroFlow-CO-Requerimientos.docx`), pero `metrics.py` ya deja
  listos los filtros y exportación a CSV que alimentarían ese tablero.
- Carga histórica completa (sin `--max-rows`): el pipeline la soporta
  y persiste lo que reciba aunque la conexión se corte (`status=partial`),
  pero no se completó un ciclo con `status=success` (`complete=True`)
  para las series más pesadas en esta sesión por la lentitud del
  servidor de DANE descrita arriba (ver "Fuentes de datos"). Ejecutar
  `extract --all` sin `--max-rows` en un horario de baja carga para la
  primera carga histórica real; puede necesitar más de un intento.
