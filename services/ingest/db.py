import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),  # DEV: 5433, Docker: 5432
        dbname=os.getenv("POSTGRES_DB", "assistance"),
        user=os.getenv("POSTGRES_USER", "brogi"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
