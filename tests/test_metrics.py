"""Known-answer tests for the reliability metrics.

Both implementations -- the SQL views (sql/02_views_metrics.sql) and the
pandas re-implementation the dashboard uses (app/metrics.py) -- are
checked against the same hand-computed numbers from the fixture in
conftest.py. Passing both proves the dashboard and the SQL layer agree,
so a formula change in one place without the other fails here.
"""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import text

import metrics
from data import EVENTS_SQL, FLIGHT_HOURS_SQL

# Expected values, derived by hand from the fixture table in conftest.py.
FLEET_HOURS = 150.0
EXPECTED_MTBF_BY_COMPONENT = {"C1": 150 / 2, "C2": 150 / 1}      # failures only
EXPECTED_MTTR_BY_COMPONENT = {"C1": (4 + 2) / 2, "C2": 6.0}
EXPECTED_AVAILABILITY = {"C1": 75 / (75 + 3), "C2": 150 / (150 + 6)}
EXPECTED_MTBF_BY_AIRCRAFT = {"A1": 100 / 2, "A2": 50 / 1}
EXPECTED_PARETO = [("C1", 2, 66.7), ("C2", 1, 100.0)]
EXPECTED_COST = {
    # category: (labor_and_parts, estimated_downtime, total)
    "cat_x": (1000 + 500, (4 + 2) * 100, 1500 + 600),
    "cat_y": (1000, 6 * 200, 1000 + 1200),
}


def sql_rows(conn, query: str) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(query))]


def assert_cost_matches(got: dict[str, tuple]) -> None:
    assert set(got) == set(EXPECTED_COST)
    for category, expected in EXPECTED_COST.items():
        assert got[category] == pytest.approx(expected), category


@pytest.fixture
def frames(fixture_db):
    events = pd.read_sql(EVENTS_SQL, fixture_db)
    events["failed_at"] = pd.to_datetime(events["failed_at"])
    events["repaired_at"] = pd.to_datetime(events["repaired_at"])
    flight_hours = pd.read_sql(FLIGHT_HOURS_SQL, fixture_db)
    flight_hours["full_date"] = pd.to_datetime(flight_hours["full_date"])
    return events, flight_hours


# ---------------------------------------------------------------- SQL views

def test_sql_mtbf_by_component(fixture_db):
    rows = sql_rows(fixture_db, "SELECT component_code, mtbf_hours FROM warehouse.v_mtbf_by_component")
    got = {r["component_code"]: float(r["mtbf_hours"]) for r in rows}
    assert got == pytest.approx(EXPECTED_MTBF_BY_COMPONENT)


def test_sql_mttr_and_availability(fixture_db):
    rows = sql_rows(
        fixture_db,
        "SELECT component_code, mttr_hours, availability FROM warehouse.v_availability_by_component",
    )
    assert {r["component_code"]: float(r["mttr_hours"]) for r in rows} == pytest.approx(
        EXPECTED_MTTR_BY_COMPONENT
    )
    assert {r["component_code"]: float(r["availability"]) for r in rows} == pytest.approx(
        EXPECTED_AVAILABILITY
    )


def test_sql_mtbf_by_aircraft(fixture_db):
    rows = sql_rows(fixture_db, "SELECT tail_number, mtbf_hours FROM warehouse.v_mtbf_by_aircraft")
    got = {r["tail_number"]: float(r["mtbf_hours"]) for r in rows}
    assert got == pytest.approx(EXPECTED_MTBF_BY_AIRCRAFT)


def test_sql_pareto(fixture_db):
    rows = sql_rows(
        fixture_db,
        "SELECT component_code, failure_count, cumulative_pct FROM warehouse.v_failure_pareto",
    )
    got = [(r["component_code"], r["failure_count"], float(r["cumulative_pct"])) for r in rows]
    assert got == EXPECTED_PARETO


def test_sql_downtime_cost(fixture_db):
    rows = sql_rows(fixture_db, "SELECT * FROM warehouse.v_downtime_cost_by_category")
    got = {
        r["component_category"]: (
            float(r["labor_and_parts_cost"]),
            float(r["estimated_downtime_cost"]),
            float(r["total_estimated_cost"]),
        )
        for r in rows
    }
    assert_cost_matches(got)
    # Ordered by total cost, most expensive first.
    assert [r["component_category"] for r in rows] == ["cat_y", "cat_x"]


def test_sql_time_between_failures(fixture_db):
    rows = sql_rows(
        fixture_db,
        """
        SELECT a.tail_number, t.component_code, t.hours_since_last_event
        FROM warehouse.v_time_between_failures t
        JOIN warehouse.dim_aircraft a ON a.aircraft_key = t.aircraft_key
        ORDER BY 1, 2, t.failed_at
        """,
    )
    got = [(r["tail_number"], r["component_code"], float(r["hours_since_last_event"])) for r in rows]
    # A1/C1 fails at 20 fh then 50 fh -> gaps 20 and 30. The scheduled event
    # (no flight-hours reading) is excluded; the replacement is included.
    assert got == [("A1", "C1", 20.0), ("A1", "C1", 30.0), ("A1", "C2", 60.0), ("A2", "C2", 15.0)]


# ------------------------------------------- pandas (what the dashboard shows)

def test_pandas_matches_expected_component_metrics(frames):
    events, flight_hours = frames
    avail = metrics.availability_by_component(events, flight_hours).set_index("component_code")
    assert avail["mtbf_hours"].to_dict() == pytest.approx(EXPECTED_MTBF_BY_COMPONENT)
    assert avail["mttr_hours"].to_dict() == pytest.approx(EXPECTED_MTTR_BY_COMPONENT)
    assert avail["availability"].to_dict() == pytest.approx(EXPECTED_AVAILABILITY)


def test_pandas_matches_expected_aircraft_mtbf(frames):
    events, flight_hours = frames
    by_ac = metrics.mtbf_by_aircraft(events, flight_hours).set_index("tail_number")
    assert by_ac["mtbf_hours"].astype(float).to_dict() == pytest.approx(EXPECTED_MTBF_BY_AIRCRAFT)


def test_pandas_matches_expected_pareto(frames):
    events, _ = frames
    p = metrics.failure_pareto(events)
    got = list(zip(p["component_code"], p["failure_count"], p["cumulative_pct"]))
    assert got == EXPECTED_PARETO


def test_pandas_matches_expected_cost(frames):
    events, _ = frames
    cost = metrics.downtime_cost_by_category(events)
    got = {
        row.component_category: (
            row.labor_and_parts_cost,
            row.estimated_downtime_cost,
            row.total_estimated_cost,
        )
        for row in cost.itertuples()
    }
    assert_cost_matches(got)
    assert list(cost["component_category"]) == ["cat_y", "cat_x"]


def test_pandas_fleet_kpis(frames):
    events, flight_hours = frames
    k = metrics.kpis(events, flight_hours)
    assert k["total_flight_hours"] == pytest.approx(FLEET_HOURS)
    assert k["failure_count"] == 3
    assert k["mtbf_hours"] == pytest.approx(150 / 3)
    assert k["mttr_hours"] == pytest.approx((4 + 2 + 6) / 3)
    assert k["availability"] == pytest.approx(50 / (50 + 4))
    assert k["total_cost"] == pytest.approx(2500 + 1800)
