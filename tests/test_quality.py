"""The data-quality checks must pass on clean data AND fail on bad data.

A check that never fails proves nothing, so each case below plants one
specific kind of bad row and asserts that exactly the matching check
reports it -- and no other check does. Some bad rows would normally be
rejected by the schema's own constraints; those cases drop the
constraint first, which simulates a load path that bypasses them (the
scenario the SQL checks exist to catch). Everything runs inside a
savepoint in the fixture's transaction and is rolled back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from fleet_reliability.quality import run_checks

EVENT_COLUMNS = """
    (event_id, aircraft_key, component_key, base_key, date_key, event_type,
     flight_hours_at_failure, failed_at, repaired_at, labor_cost, parts_cost)
"""

BAD_DATA_CASES = {
    "test_repair_after_failure.sql": [
        "ALTER TABLE warehouse.fact_maintenance_event DROP CONSTRAINT chk_repair_after_failure",
        f"""INSERT INTO warehouse.fact_maintenance_event {EVENT_COLUMNS}
            VALUES (10, 2, 2, 1, 20240108, 'failure', 40,
                    '2024-01-08 05:00', '2024-01-08 01:00', 100, 100)""",
    ],
    "test_no_orphan_foreign_keys.sql": [
        "ALTER TABLE warehouse.fact_maintenance_event "
        "DROP CONSTRAINT fact_maintenance_event_aircraft_key_fkey",
        f"""INSERT INTO warehouse.fact_maintenance_event {EVENT_COLUMNS}
            VALUES (11, 999, 1, 1, 20240108, 'failure', 40,
                    '2024-01-08 00:00', '2024-01-08 01:00', 100, 100)""",
    ],
    "test_no_overlapping_downtime.sql": [
        # A1/C1 is already under repair 2024-01-02 00:00-04:00 (event 1).
        f"""INSERT INTO warehouse.fact_maintenance_event {EVENT_COLUMNS}
            VALUES (12, 1, 1, 1, 20240102, 'failure', 25,
                    '2024-01-02 03:00', '2024-01-02 05:00', 100, 100)""",
    ],
    "test_non_negative_amounts.sql": [
        f"""INSERT INTO warehouse.fact_maintenance_event {EVENT_COLUMNS}
            VALUES (13, 2, 2, 1, 20240109, 'failure', 45,
                    '2024-01-09 00:00', '2024-01-09 01:00', -50, 100)""",
    ],
}


def failing_checks(conn) -> set[str]:
    return {name for name, rows in run_checks(conn).items() if rows}


def test_all_checks_pass_on_clean_fixture(fixture_db):
    assert failing_checks(fixture_db) == set()


@pytest.mark.parametrize("expected_failure", sorted(BAD_DATA_CASES))
def test_check_catches_its_bad_row(fixture_db, expected_failure):
    savepoint = fixture_db.begin_nested()
    try:
        for statement in BAD_DATA_CASES[expected_failure]:
            fixture_db.execute(text(statement))
        assert failing_checks(fixture_db) == {expected_failure}
    finally:
        savepoint.rollback()


def test_negative_flight_hours_are_caught(fixture_db):
    savepoint = fixture_db.begin_nested()
    try:
        fixture_db.execute(text(
            "ALTER TABLE warehouse.fact_flight_hours DROP CONSTRAINT fact_flight_hours_flight_hours_check"
        ))
        fixture_db.execute(text(
            "UPDATE warehouse.fact_flight_hours SET flight_hours = -1 "
            "WHERE aircraft_key = 1 AND date_key = 20240110"
        ))
        assert failing_checks(fixture_db) == {"test_non_negative_amounts.sql"}
    finally:
        savepoint.rollback()
