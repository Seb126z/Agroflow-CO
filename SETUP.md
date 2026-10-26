# Cómo correr AgroFlow-CO en tu máquina

Guía paso a paso para clonar el repo y dejar todo funcionando: pipeline de
datos (Python) → PostgreSQL → app web (Node.js) y/o dashboard (Power BI).
Pensada para Windows con PowerShell, que es donde se desarrolló el proyecto.

No hace falta Docker: en este proyecto se usa PostgreSQL instalado
directamente en Windows (más simple y evita problemas con WSL2).

## 0) Requisitos previos

Instala esto si no lo tienes (con [winget](https://learn.microsoft.com/windows/package-manager/winget/), ya viene con Windows 10/11):

```bash
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id PostgreSQL.PostgreSQL.17 -e --accept-package-agreements --accept-source-agreements
```

El instalador de PostgreSQL es pesado (extrae pgAdmin 4 con muchísimos
archivos chicos) y puede tardar 20-40 minutos sin que eso signifique que
está colgado. Durante la instalación te va a pedir una **contraseña para
el superusuario `postgres`** — elige una y anótala, la necesitas en el
paso 1. Deja el puerto en el valor por defecto (**5432**).

Verifica que el servicio quedó corriendo:

```bash
Get-Service postgresql-x64-17
```

(El nombre exacto del servicio puede variar un poco según la versión que
te instale winget; si no es `postgresql-x64-17`, usa `Get-Service *postgresql*`
para encontrarlo.)

## 1) Crear el rol y la base de datos

Con PostgreSQL corriendo, crea el usuario y la base que usa el proyecto
(coinciden con `.env.example`, así no tienes que tocar configuración):

```bash
$env:PGPASSWORD = "<la-contraseña-de-postgres-que-elegiste>"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE ROLE agroflow LOGIN PASSWORD 'agroflow_dev';"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE DATABASE agroflow OWNER agroflow;"
```

Si tu instalador de PostgreSQL quedó en otra ruta (por ejemplo otra
versión), ajusta la ruta a `psql.exe`.

## 2) Clonar el repo y preparar Python

```bash
git clone <URL-del-repositorio>
cd AgroFlow-CO
```

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
Copy-Item .env.example .env
```

El `.env` por defecto ya apunta a `localhost:5432`, base `agroflow`,
usuario `agroflow`, contraseña `agroflow_dev` — exactamente lo que
creaste en el paso 1. Si usaste otros valores, edita `.env` para que
coincidan.

## 3) Crear el esquema y cargar datos reales

```bash
python -m src.agroflow.cli init-db
```

Esto crea las tablas, vistas e índices (incluye el índice de texto que
hace rápidas las búsquedas por producto/ciudad).

Ahora extrae datos reales desde el servicio SIPSA-DANE:

```bash
python -m src.agroflow.cli extract --all
```

**Importante:** el servicio de DANE es lento y en respuestas grandes corta
la conexión antes de terminar — es un comportamiento conocido del
servidor, no un error del pipeline (ver `docs/03-mapeo-campos.md`). El
pipeline guarda lo que alcanza a recibir como una corrida "parcial" en vez
de perderlo. Una carga completa de las 4 fuentes puede tardar bastante
(en la práctica, varios minutos y potencialmente más de un intento). Si
solo quieres probar rápido que todo funciona, usa:

```bash
python -m src.agroflow.cli extract --source promediosSipsaCiudad --max-rows 1000
```

Verifica que haya datos:

```bash
python -m src.agroflow.cli metrics --product papa
```

## 4) Levantar la app web (Node.js)

```bash
cd webapp
npm install
npm start
```

Abre [http://localhost:3000](http://localhost:3000). La app web es de
**solo lectura**: consulta la base de datos que acabas de cargar, no
vuelve a tocar SIPSA. Ver [webapp/README.md](webapp/README.md) para el
detalle de los endpoints.

## 5) (Opcional) Dashboard en Power BI

Si tienes [Power BI Desktop](https://www.microsoft.com/download/details.aspx?id=58494)
instalado, puedes abrir `dashboard.pbix` y reemplazar su origen de datos
para que apunte a tu propio PostgreSQL:

1. Abre `dashboard.pbix`.
2. **Inicio → Transformar datos → Configuración de origen de datos** →
   selecciona el origen PostgreSQL → **Cambiar origen** → confirma
   `127.0.0.1` / `agroflow` (ajusta si usaste otros valores).
3. Te pedirá credenciales: pestaña **Database**, usuario `agroflow`,
   contraseña `agroflow_dev`.
4. **Cerrar y aplicar**.

Si prefieres armarlo desde cero, las vistas `v_sipsa_variacion_mensual` y
`v_sipsa_precio_mensual_producto` ya traen los datos listos para graficar
con filtros dinámicos por producto, ciudad y fecha.

## Automatizar la carga (opcional)

Para que los datos se actualicen solos periódicamente (RF-10), hay un
script para Task Scheduler de Windows: ver la sección "Automatización"
en [README.md](README.md).

## Problemas comunes

- **`init-db` o `extract` no conectan a PostgreSQL**: confirma que el
  servicio está corriendo (`Get-Service *postgresql*`) y que los valores
  en `.env` coinciden con el usuario/base/contraseña que creaste.
- **Una consulta en la web tarda mucho**: confirma que corriste
  `init-db` *después* de que existiera `sql/002_trgm_indexes.sql` (si
  clonaste el repo completo, ya está incluido — `init-db` aplica todos
  los archivos `.sql` en orden automáticamente).
- **El pipeline se queda "parcial" en vez de "completo"**: es normal con
  las fuentes grandes (`promediosSipsaMesMadr`, `SemanaMadr`, `Parcial`)
  por la lentitud del servidor de DANE descrita arriba. Los datos
  recibidos sí quedan guardados; puedes volver a correr `extract` para
  intentar completar más.
