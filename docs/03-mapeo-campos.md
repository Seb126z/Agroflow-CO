# Mapeo de campos SIPSA → esquema AgroFlow-CO

Resultado del paso 2-5 del plan (`docs/01-plan.md`): WSDL inspeccionado,
operaciones reales invocadas contra el servicio en producción y
respuestas crudas guardadas en `data/raw/` antes de definir este mapeo.

## WSDL real

```
http://appweb.dane.gov.co:80/sipsaWS/SrvSipsaUpraBeanService?wsdl
```

Servicio: `SrvSipsaUpraBeanService` / Puerto: `SrvSipsaUpraPort`.

> **Nota de endpoint:** el WSDL anuncia el endpoint SOAP en
> `http://appweb.dane.gov.co:80/...`. Ese puerto 80 responde **301** hacia
> `https://appweb.dane.gov.co:443/...`, y al reenviar el `POST` tras la
> redirección el servidor cae al handler por defecto y devuelve una
> página HTML ("Web Services") en lugar del sobre SOAP. Por eso
> `src/agroflow/soap_raw.py` llama directamente al endpoint HTTPS real.
> `zeep` (usado solo para `inspect_wsdl.py`) tiene el mismo problema si no
> se le fuerza `client.service._binding_options['address']`.

Operaciones disponibles (6 en total). Las 4 primeras son precios
mayoristas y son las que implementa el pipeline (alcance definido en
`docs/AgroFlow-CO-Requerimientos.docx`: "la primera versión se concentra
en precios mayoristas"). Las otras 2 (insumos y abastecimientos) quedan
fuera de alcance por ahora.

| Operación SOAP | Implementada | Periodicidad | Cobertura observada en vivo |
|---|---|---|---|
| `promediosSipsaMesMadr` | Sí | Mensual | desde ~2023-02 |
| `promediosSipsaSemanaMadr` | Sí | Semanal | desde ~2025-11 (ventana móvil, no se confirmó el límite inferior real por corte de conexión) |
| `promediosSipsaParcial` | Sí | Semanal (semana en curso/parcial) | desde ~2020-02 |
| `promediosSipsaCiudad` | Sí | Diario (boletín por ciudad) | varios días recientes, orden descendente por `regId` |
| `promedioAbasSipsaMesMadr` | No (fuera de alcance: abastecimiento/toneladas, no precio) | Mensual | — |
| `consultarInsumosSipsaMesMadr(int)` | No (fuera de alcance: insumos agropecuarios, no precio mayorista) | Mensual | — |

Ninguna operación acepta filtros de fecha/producto/ubicación: siempre
devuelven el historial completo disponible. Por eso el pipeline no
puede pedir "solo lo nuevo" al servicio; la incrementalidad se maneja
en la carga (upsert por `natural_key`, ver RF-09).

## Campos crudos por operación → columna unificada

Tabla destino: `sipsa_price_observations` (`sql/001_initial_schema.sql`).

### `promediosSipsaMesMadr` / `promediosSipsaSemanaMadr`
(Promedios mayoristas por central de abastos, mensual/semanal)

| Campo SIPSA | Columna AgroFlow | Notas |
|---|---|---|
| `artiNombre` | `product` | Nombre del artículo |
| `fuenNombre` | `market` | Central de abastos / fuente |
| `fechaMesIni` / `fechaIni` | `observation_date` | Inicio del periodo |
| `minimoKg` | `min_price` | Precio mínimo por kg |
| `maximoKg` | `max_price` | Precio máximo por kg |
| `promedioKg` | `average_price` | Precio promedio por kg |
| `fechaCreacion` | `source_updated_at` | Marca de creación en origen |
| — | `unit` | Fijo `"kg"` (todas las series "Kg" del servicio) |
| — | `period_type` | `"mensual"` / `"semanal"` |
| `artiId`, `fuenId`, `futiId`, `tmpMayoMesId`/`tmpMayoSemId`, `enviado` | *(sin usar)* | IDs internos de DANE, se conservan en `raw_payload` |

### `promediosSipsaParcial`
(Promedios mayoristas semana en curso, con ubicación administrativa y grupo)

| Campo SIPSA | Columna AgroFlow | Notas |
|---|---|---|
| `artiNombre` | `product` | |
| `grupNombre` | `product_group` | Grupo de alimento (ej. "VERDURAS Y HORTALIZAS") |
| `fuenNombre` | `market` | |
| `deptNombre` | `department` | Departamento |
| `muniNombre` | `city` | Municipio |
| `enmaFecha` | `observation_date` | |
| `minimoKg` / `maximoKg` / `promedioKg` | `min_price` / `max_price` / `average_price` | |
| — | `period_type` | `"semanal_parcial"` |
| `fuenId`, `futiId`, `muniId`, `idArtiSemana` | *(sin usar)* | se conservan en `raw_payload` |

### `promediosSipsaCiudad`
(Boletín diario de precio promedio por ciudad)

| Campo SIPSA | Columna AgroFlow | Notas |
|---|---|---|
| `producto` | `product` | |
| `ciudad` | `city` | |
| `fechaCaptura` | `observation_date` | |
| `precioPromedio` | `average_price` | Esta operación **no** entrega mínimo/máximo |
| `fechaCreacion` | `source_updated_at` | |
| — | `market`, `unit` | `NULL` (el dato no viene en esta operación) |
| — | `period_type` | `"diario"` |
| `codProducto`, `regId`, `enviado` | *(sin usar)* | se conservan en `raw_payload` |

## Validaciones aplicadas (RF-06)

Implementadas en `src/agroflow/transform.py::validate`. Se descarta
(no se corrige ni se inventa) una fila si:
- `observation_date` no es una fecha parseable.
- `average_price` es nulo o negativo.
- `product` es nulo o vacío.
- hay `min_price` y `max_price` simultáneamente y `min_price > max_price`.

Cada corrida registra cuántas filas de cada tipo se descartaron
(`logger.warning`), y el conteo de "recibidas vs. cargadas" queda en
`sipsa_extraction_runs` para trazabilidad.

## Deduplicación (RF-09)

Como el servicio no expone un ID de negocio estable para estas
operaciones (los IDs como `regId`/`idArtiSemana` son correlativos
internos de DANE, no claves de negocio), se calcula una
`natural_key = sha256(source_system | observation_date | department |
city | market | product)`. Es una columna `UNIQUE` en
`sipsa_price_observations`, y la carga usa
`INSERT ... ON CONFLICT (natural_key) DO UPDATE` para que una misma
observación (mismo producto/mercado/fecha) actualice el precio en vez
de duplicarse si DANE corrige un valor en una corrida posterior.

## Comportamiento real del servidor observado en esta sesión

Las 4 operaciones de "promedios" no reciben parámetros y devuelven
**todo el historial disponible** en cada llamada (no hay forma de pedir
solo el último mes). En pruebas reales contra el servicio en producción
(octubre 2026):

- Una llamada sin límite a `promediosSipsaSemanaMadr` transfirió ~65 MB
  y la conexión se cortó a mitad de un registro tras varios minutos
  (`IncompleteRead`/XML truncado), sin terminar.
- Lo mismo ocurrió con `promediosSipsaCiudad` en dos intentos distintos.
- Con filas acotadas (`--max-rows`) para pruebas, las 4 operaciones
  respondieron correctamente y de forma rápida.

Por eso `soap_raw.call_streaming` parsea de forma incremental
(`lxml.etree.XMLPullParser`) y **conserva las filas ya recibidas** si la
conexión se corta, marcando la corrida como `partial` en vez de
descartar todo o fallar. Una sincronización completa real debe
ejecutarse esperando varios minutos y aceptando que puede requerir más
de un intento (ver `README.md`, sección de automatización).
