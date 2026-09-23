"""Single shared entry point for the project's database connection.

Every other module (ETL, quality checks, the Streamlit app) imports
get_engine() from here instead of reading DATABASE_URL itself, so there
is exactly one place that knows how the app connects to Postgres.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql://fleet:fleet_dev_pw@localhost:5433/fleet_reliability"


def get_engine() -> Engine:
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    return create_engine(url, pool_pre_ping=True)
