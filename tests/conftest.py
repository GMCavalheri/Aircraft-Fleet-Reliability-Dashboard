"""Shared fixtures for the database-backed tests.

`fixture_db` opens a connection to the local Postgres, starts a
transaction, replaces the warehouse contents with a tiny hand-built
dataset (FIXTURE_SQL), and rolls everything back afterwards -- so the
tests never leave a trace in the real warehouse. Postgres DDL and
TRUNCATE are transactional, which is what makes this safe.

If the database isn't reachable (e.g. `docker compose up` hasn't been
run), these tests are skipped rather than failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from fleet_reliability.db import get_engine

# The Streamlit app's modules (metrics.py, data.py) live in app/ as flat
# modules, the way Streamlit imports them; make them importable here too.
APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

# Hand-computable fixture. Exposure: A1 flies 10 days x 10 h = 100 h,
# A2 flies 10 days x 5 h = 50 h, fleet total 150 h.
#
#   event  aircraft component  type         repair  labor+parts  fh_at_event
#   1      A1       C1         failure      4 h     1000         20
#   2      A1       C1         failure      2 h      500         50
#   3      A2       C2         failure      6 h     1000         15
#   4      A2       C1         scheduled    1 h       10         -
#   5      A1       C2         replacement  3 h     1020         60
#
# C1 is category cat_x at $100/h downtime, C2 is cat_y at $200/h.
FIXTURE_SQL = """
TRUNCATE warehouse.fact_maintenance_event, warehouse.fact_flight_hours,
         warehouse.dim_aircraft, warehouse.dim_component,
         warehouse.dim_base, warehouse.dim_date;

INSERT INTO warehouse.dim_date
SELECT to_char(d, 'YYYYMMDD')::int, d::date,
       EXTRACT(YEAR FROM d), EXTRACT(QUARTER FROM d), EXTRACT(MONTH FROM d),
       to_char(d, 'FMMonth'), EXTRACT(DAY FROM d),
       EXTRACT(ISODOW FROM d) - 1, EXTRACT(ISODOW FROM d) >= 6
FROM generate_series('2024-01-01'::date, '2024-01-10'::date, interval '1 day') AS d;

INSERT INTO warehouse.dim_aircraft (aircraft_key, tail_number, aircraft_type, manufacturer, in_service_date)
VALUES (1, 'A1', 'A320-200', 'Airbus', '2024-01-01'),
       (2, 'A2', 'B737-800', 'Boeing', '2024-01-01');

INSERT INTO warehouse.dim_component
    (component_key, component_code, ata_chapter, component_name, component_category,
     criticality, unit_cost, hourly_downtime_cost)
VALUES (1, 'C1', '24', 'Component one', 'cat_x', 'high', 1000, 100),
       (2, 'C2', '32', 'Component two', 'cat_y', 'critical', 2000, 200);

INSERT INTO warehouse.dim_base (base_key, base_code, base_name, region, country)
VALUES (1, 'B1', 'Base one', 'Region', 'Country');

INSERT INTO warehouse.fact_flight_hours (aircraft_key, date_key, flight_hours, flight_cycles)
SELECT a.aircraft_key, to_char(d, 'YYYYMMDD')::int, a.hours, 2
FROM (VALUES (1, 10.0), (2, 5.0)) AS a(aircraft_key, hours)
CROSS JOIN generate_series('2024-01-01'::date, '2024-01-10'::date, interval '1 day') AS d;

INSERT INTO warehouse.fact_maintenance_event
    (event_id, aircraft_key, component_key, base_key, date_key, event_type,
     failure_mode, severity, flight_hours_at_failure, failed_at, repaired_at,
     labor_cost, parts_cost)
VALUES
    (1, 1, 1, 1, 20240102, 'failure', 'wear', 'minor', 20,
     '2024-01-02 00:00', '2024-01-02 04:00', 100, 900),
    (2, 1, 1, 1, 20240105, 'failure', 'wear', 'major', 50,
     '2024-01-05 00:00', '2024-01-05 02:00', 50, 450),
    (3, 2, 2, 1, 20240103, 'failure', 'leak', 'minor', 15,
     '2024-01-03 00:00', '2024-01-03 06:00', 300, 700),
    (4, 2, 1, 1, 20240104, 'scheduled', NULL, NULL, NULL,
     '2024-01-04 00:00', '2024-01-04 01:00', 10, 0),
    (5, 1, 2, 1, 20240106, 'replacement', NULL, NULL, 60,
     '2024-01-06 00:00', '2024-01-06 03:00', 20, 1000);
"""


@pytest.fixture
def fixture_db():
    engine = get_engine()
    try:
        conn = engine.connect()
    except OperationalError:
        pytest.skip("local Postgres not reachable -- run `docker compose up -d`")

    trans = conn.begin()
    try:
        conn.execute(text(FIXTURE_SQL))
        yield conn
    finally:
        trans.rollback()
        conn.close()
