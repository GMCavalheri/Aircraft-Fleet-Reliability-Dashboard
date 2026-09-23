"""Streamlit-side database connection.

Wraps fleet_reliability.db so the engine is built once per session
(st.cache_resource) instead of once per rerun, and so the same code
works both locally (DATABASE_URL from .env) and on Streamlit Cloud
(DATABASE_URL from st.secrets) without an if/else scattered through
the app.
"""

from __future__ import annotations

import os

import streamlit as st
from sqlalchemy import Engine, create_engine

from fleet_reliability.db import DEFAULT_DATABASE_URL


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    url = None
    if hasattr(st, "secrets"):
        try:
            url = st.secrets.get("DATABASE_URL")
        except Exception:
            url = None
    url = url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    return create_engine(url, pool_pre_ping=True)
