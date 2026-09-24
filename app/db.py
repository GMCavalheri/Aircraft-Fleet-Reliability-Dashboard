"""Streamlit-side database connection.

Wraps fleet_reliability.db so the engine is built once per session
(st.cache_resource) instead of once per rerun. The connection URL comes
from DATABASE_URL in .env, the same as the ETL and quality scripts.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from fleet_reliability.db import get_engine as _get_engine


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    return _get_engine()
