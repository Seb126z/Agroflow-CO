import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    sipsa_wsdl: str = os.getenv(
        "SIPSA_WSDL",
        "http://appweb.dane.gov.co:80/sipsaWS/SrvSipsaUpraBeanService?wsdl"
    )
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "agroflow")
    postgres_user: str = os.getenv("POSTGRES_USER", "agroflow")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "agroflow_dev")
    # Vacío para Postgres local; "require" para proveedores en la nube
    # como Neon/Supabase, que exigen conexión cifrada.
    postgres_sslmode: str = os.getenv("POSTGRES_SSLMODE", "")

settings = Settings()
