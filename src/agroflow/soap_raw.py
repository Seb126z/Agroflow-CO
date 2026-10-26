"""Cliente SOAP ligero para el servicio SIPSA-DANE.

El WSDL publicado anuncia el endpoint en:
    http://appweb.dane.gov.co:80/sipsaWS/SrvSipsaUpraBeanService

Ese endpoint responde 301 -> https://appweb.dane.gov.co:443/... y el
servidor SOAP (JAX-WS) no reprocesa correctamente un POST tras seguir
la redirección (algunos clientes HTTP convierten el POST en GET al
seguirla), lo que hace que devuelva la página HTML de información del
servicio en lugar del sobre SOAP. Por eso se llama directamente al
endpoint HTTPS.

Se usa `requests` en modo streaming en lugar de `zeep` para las
operaciones de "promedios" porque no reciben parámetros y devuelven el
historial completo (varios años, decenas de MB en XML); zeep construye
un árbol de objetos Python por cada <return> y es demasiado lento para
ese volumen. Aquí se parsea el XML de forma incremental (iterparse) y
se van entregando los registros a medida que llegan, confirmando datos
reales tal como los envía el servidor.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from lxml import etree

logger = logging.getLogger(__name__)

SOAP_NS = "http://servicios.sipsa.co.gov.dane/"
ENVELOPE_NS = "http://www.w3.org/2003/05/soap-envelope"

# El WSDL anuncia el endpoint en puerto 80 (HTTP); en la práctica ese
# puerto redirige (301) a HTTPS y la redirección rompe el POST SOAP.
# Se fuerza aquí el endpoint HTTPS real.
SOAP_ENDPOINT = "https://appweb.dane.gov.co:443/sipsaWS/SrvSipsaUpraBeanService"

DEFAULT_CONNECT_TIMEOUT = 15
DEFAULT_READ_TIMEOUT = 600


class SipsaSoapError(RuntimeError):
    """Error al invocar una operación del servicio SIPSA."""


@dataclass
class StreamResult:
    """Resultado de una extracción en streaming."""

    rows: list[dict]
    complete: bool
    bytes_received: int
    http_status: int


def _build_envelope(operation: str, int_arg: int | None = None) -> bytes:
    if int_arg is None:
        body = f'<ns0:{operation} xmlns:ns0="{SOAP_NS}"/>'
    else:
        body = (
            f'<ns0:{operation} xmlns:ns0="{SOAP_NS}">'
            f"<arg0>{int(int_arg)}</arg0>"
            f"</ns0:{operation}>"
        )
    envelope = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f'<soap-env:Envelope xmlns:soap-env="{ENVELOPE_NS}">'
        f"<soap-env:Body>{body}</soap-env:Body>"
        "</soap-env:Envelope>"
    )
    return envelope.encode("utf-8")


def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def call_streaming(
    operation: str,
    int_arg: int | None = None,
    *,
    max_rows: int | None = None,
    record_tag: str = "return",
    read_timeout: int = DEFAULT_READ_TIMEOUT,
) -> StreamResult:
    """Invoca una operación SOAP de SIPSA y parsea la respuesta incrementalmente.

    Devuelve los registros ya recibidos aunque la conexión se corte antes
    de terminar (``complete=False``) para no perder datos reales ya
    entregados por el servidor en respuestas muy grandes.
    """
    envelope = _build_envelope(operation, int_arg)
    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "User-Agent": "AgroFlow-CO/0.1 (+https://github.com/)",
    }
    session = _make_session()
    rows: list[dict] = []
    bytes_received = 0
    complete = False
    status_code = 0

    try:
        with session.post(
            SOAP_ENDPOINT,
            data=envelope,
            headers=headers,
            stream=True,
            timeout=(DEFAULT_CONNECT_TIMEOUT, read_timeout),
        ) as response:
            status_code = response.status_code
            if status_code != 200:
                raise SipsaSoapError(
                    f"{operation}: HTTP {status_code} inesperado del servicio SIPSA"
                )
            content_type = response.headers.get("Content-Type", "")
            if "xml" not in content_type and "soap" not in content_type:
                # El servidor cae al handler por defecto (página HTML de info)
                raise SipsaSoapError(
                    f"{operation}: el servidor no devolvió XML/SOAP "
                    f"(Content-Type={content_type!r}); revisar endpoint/redirección"
                )

            parser = etree.XMLPullParser(events=("end",), recover=False)

            def iter_chunks():
                nonlocal bytes_received
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    bytes_received += len(chunk)
                    yield chunk

            fault_text: str | None = None
            try:
                for chunk in iter_chunks():
                    parser.feed(chunk)
                    for _, elem in parser.read_events():
                        tag = etree.QName(elem.tag).localname
                        if tag == record_tag:
                            rows.append(
                                {
                                    etree.QName(child.tag).localname: child.text
                                    for child in elem
                                }
                            )
                            elem.clear()
                            if max_rows is not None and len(rows) >= max_rows:
                                complete = False
                                raise _StopEarly()
                        elif tag == "Fault":
                            fault_text = etree.tostring(elem, encoding="unicode")
                parser.close()
                complete = True
            except _StopEarly:
                complete = False
            except (etree.XMLSyntaxError, requests.exceptions.ChunkedEncodingError,
                     requests.exceptions.ConnectionError):
                # Conexión cortada a mitad de transmisión (observado en
                # producción con respuestas grandes del servicio SIPSA) o
                # XML incompleto: se conservan los registros ya parseados
                # y se marca la extracción como incompleta en lugar de
                # perder lo ya recibido.
                logger.warning(
                    "soap.call operation=%s conexión cortada tras %d filas / %d bytes",
                    operation, len(rows), bytes_received,
                )
                complete = False

            if fault_text:
                raise SipsaSoapError(f"{operation}: SOAP Fault recibido: {fault_text}")
    except requests.exceptions.RequestException as exc:
        raise SipsaSoapError(f"{operation}: error de red: {exc}") from exc
    finally:
        session.close()

    logger.info(
        "soap.call operation=%s rows=%d bytes=%d complete=%s",
        operation,
        len(rows),
        bytes_received,
        complete,
    )
    return StreamResult(
        rows=rows, complete=complete, bytes_received=bytes_received, http_status=status_code
    )


class _StopEarly(Exception):
    pass
