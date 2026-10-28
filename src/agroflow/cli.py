"""CLI de AgroFlow-CO.

Ejemplos (PowerShell, con el venv activado):

    python -m src.agroflow.cli inspect-wsdl
    python -m src.agroflow.cli init-db
    python -m src.agroflow.cli extract --source promediosSipsaCiudad
    python -m src.agroflow.cli extract --all
    python -m src.agroflow.cli metrics --product papa --export data/processed/papa.csv
    python -m src.agroflow.cli run-forever --interval-hours 24
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .transform import SOURCE_SPECS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("agroflow.cli")

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def cmd_inspect_wsdl(_args: argparse.Namespace) -> int:
    from . import inspect_wsdl  # noqa: F401  (el import ya ejecuta la inspección)

    return 0


def cmd_init_db(_args: argparse.Namespace) -> int:
    from . import db

    # Aplica todos los archivos .sql en orden (001_, 002_, ...) para que
    # una base nueva quede igual de actualizada que una que se fue
    # migrando paso a paso.
    for sql_path in sorted(SQL_DIR.glob("*.sql")):
        db.apply_schema(str(sql_path))
        print(f"Esquema aplicado desde {sql_path}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    from . import pipeline

    sources = list(SOURCE_SPECS) if args.all else [args.source]
    exit_code = 0
    for source in sources:
        record = pipeline.run_source(
            source,
            max_rows=args.max_rows,
            persist=not args.no_persist,
            store_raw_payload=not args.no_raw_payload,
        )
        print(
            f"[{record['status']}] {source}: recibidas={record['rows_received']} "
            f"cargadas={record['rows_loaded']} raw={record['raw_file_path']}"
            + (f" error={record['error_message']}" if record["error_message"] else "")
        )
        if record["status"] == "failed":
            exit_code = 1
    return exit_code


def cmd_metrics(args: argparse.Namespace) -> int:
    from . import metrics

    if args.top_volatiles:
        df = metrics.top_productos_mas_volatiles(limit=args.limit)
    elif args.by_city:
        df = metrics.resumen_por_ciudad(desde=args.desde)
    else:
        df = metrics.precio_mensual_por_producto(
            product=args.product, city=args.city, market=args.market,
            desde=args.desde, hasta=args.hasta,
        )
    if df.empty:
        print("Sin resultados para los filtros indicados.")
    else:
        print(df.to_string(index=False))
    if args.export:
        metrics.export_csv(df, args.export)
        print(f"Exportado a {args.export}")
    return 0


def cmd_run_forever(args: argparse.Namespace) -> int:
    from . import pipeline

    logger.info("run-forever: intervalo=%sh", args.interval_hours)
    while True:
        for record in pipeline.run_all(max_rows=args.max_rows):
            logger.info("run-forever resultado: %s", record)
        time.sleep(args.interval_hours * 3600)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agroflow", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inspect-wsdl", help="Inspecciona el WSDL de SIPSA").set_defaults(
        func=cmd_inspect_wsdl
    )

    sub.add_parser("init-db", help="Crea/actualiza el esquema en PostgreSQL").set_defaults(
        func=cmd_init_db
    )

    p_extract = sub.add_parser("extract", help="Ejecuta el pipeline para una o todas las fuentes")
    p_extract.add_argument("--source", choices=list(SOURCE_SPECS), help="Operación SIPSA a extraer")
    p_extract.add_argument("--all", action="store_true", help="Extraer todas las fuentes soportadas")
    p_extract.add_argument(
        "--max-rows", type=int, default=None,
        help="Límite de filas (solo pruebas: corta la descarga antes de terminar)",
    )
    p_extract.add_argument(
        "--no-persist", action="store_true",
        help="No escribir en PostgreSQL (solo extraer y normalizar, útil sin DB disponible)",
    )
    p_extract.add_argument(
        "--no-raw-payload", action="store_true",
        help="No guardar el JSON crudo por fila (columna raw_payload queda NULL); "
             "pensado para la copia liviana en la nube que alimenta la web pública",
    )
    p_extract.set_defaults(func=cmd_extract)

    p_metrics = sub.add_parser("metrics", help="Consulta métricas ya cargadas en PostgreSQL")
    p_metrics.add_argument("--product", help="Filtrar por producto (coincidencia parcial)")
    p_metrics.add_argument("--city", help="Filtrar por ciudad")
    p_metrics.add_argument("--market", help="Filtrar por mercado/central de abastos")
    p_metrics.add_argument("--desde", help="Fecha/mes mínimo (YYYY-MM-DD)")
    p_metrics.add_argument("--hasta", help="Fecha/mes máximo (YYYY-MM-DD)")
    p_metrics.add_argument("--top-volatiles", action="store_true", help="Top productos más volátiles")
    p_metrics.add_argument("--by-city", action="store_true", help="Resumen agregado por ciudad")
    p_metrics.add_argument("--limit", type=int, default=10)
    p_metrics.add_argument("--export", help="Ruta CSV de exportación (para Looker Studio u otra herramienta)")
    p_metrics.set_defaults(func=cmd_metrics)

    p_forever = sub.add_parser("run-forever", help="Automatiza ejecuciones periódicas (RF-10)")
    p_forever.add_argument("--interval-hours", type=float, default=24.0)
    p_forever.add_argument("--max-rows", type=int, default=None)
    p_forever.set_defaults(func=cmd_run_forever)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "extract" and not args.all and not args.source:
        parser.error("extract requiere --source <operación> o --all")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
