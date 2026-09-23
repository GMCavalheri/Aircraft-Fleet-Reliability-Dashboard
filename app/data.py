"""Cached data loaders. The event and flight-hours tables are small
(a few MB) at this project's fleet size, so the dashboard loads them
once per session and does filtering/aggregation in pandas -- the same
formulas as the Phase 4 SQL views, just recomputed on whatever slice
the sidebar filters select.

This is an explicit scalability trade-off: at fleet sizes where the
warehouse no longer fits comfortably in memory, filters should instead
be pushed down into parametrized SQL (WHERE + GROUP BY) so Postgres
does the aggregation. Documented here rather than silently assumed.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db import get_engine

EVENTS_SQL = """
SELECT
    f.event_id, f.event_type, f.failure_mode, f.severity,
    f.flight_hours_at_failure, f.failed_at, f.repaired_at,
    f.repair_hours, f.labor_cost, f.parts_cost, f.downtime_cost,
    a.tail_number, a.aircraft_type, a.manufacturer,
    c.component_code, c.component_name, c.component_category,
    c.criticality, c.hourly_downtime_cost,
    b.base_code, b.base_name, b.region
FROM warehouse.fact_maintenance_event f
JOIN warehouse.dim_aircraft a  ON a.aircraft_key = f.aircraft_key
JOIN warehouse.dim_component c ON c.component_key = f.component_key
JOIN warehouse.dim_base b      ON b.base_key = f.base_key
"""

FLIGHT_HOURS_SQL = """
SELECT fh.aircraft_key, a.tail_number, a.aircraft_type, d.full_date,
       fh.flight_hours, fh.flight_cycles
FROM warehouse.fact_flight_hours fh
JOIN warehouse.dim_aircraft a ON a.aircraft_key = fh.aircraft_key
JOIN warehouse.dim_date d     ON d.date_key = fh.date_key
"""

TIME_BETWEEN_FAILURES_SQL = "SELECT * FROM warehouse.v_time_between_failures"


@st.cache_data(ttl=600, show_spinner="Loading maintenance events...")
def load_events() -> pd.DataFrame:
    df = pd.read_sql(EVENTS_SQL, get_engine())
    df["failed_at"] = pd.to_datetime(df["failed_at"])
    df["repaired_at"] = pd.to_datetime(df["repaired_at"])
    return df


@st.cache_data(ttl=600, show_spinner="Loading flight hours...")
def load_flight_hours() -> pd.DataFrame:
    df = pd.read_sql(FLIGHT_HOURS_SQL, get_engine())
    df["full_date"] = pd.to_datetime(df["full_date"])
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_time_between_failures() -> pd.DataFrame:
    df = pd.read_sql(TIME_BETWEEN_FAILURES_SQL, get_engine())
    df["failed_at"] = pd.to_datetime(df["failed_at"])
    return df
