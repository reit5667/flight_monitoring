import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "flight_monitor"),
        user=os.getenv("POSTGRES_USER", "flight_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )
