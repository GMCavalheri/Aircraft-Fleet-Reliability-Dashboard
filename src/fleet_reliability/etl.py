"""ETL: staging CSVs -> staging schema -> warehouse star schema.

Each run is a full reload (truncate + insert), not incremental CDC --
the right trade-off for a batch-generated, portfolio-scale dataset. It
keeps the pipeline trivially idempotent: run it as many times as you
like on the same input and you get the same warehouse state.

Order matters:
  1. staging  (raw load, 1:1 with the CSVs)
  2. dim_date (derived from the min/max dates actually present)
  3. dimensions (aircraft, component, base) -- upserted on natural key
  4. facts (maintenance_event, flight_hours) -- resolved to surrogate
     keys by joining staging to the now-populated dimensions
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from fleet_reliability.db import get_engine

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

STAGING_TABLES = {
    "stg_aircraft": "aircraft.csv",
    "stg_component": "component.csv",
    "stg_base": "base.csv",
    "stg_maintenance_event": "maintenance_event.csv",
    "stg_flight_hours": "flight_hours.csv",
}


def load_staging(engine: Engine, data_dir: Path = DATA_DIR) -> None:
    for table, filename in STAGING_TABLES.items():
        df = pd.read_csv(data_dir / filename)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE staging.{table} CASCADE"))
            df.to_sql(table, conn, schema="staging", if_exists="append", index=False)
        print(f"staging.{table}: {len(df):>7,} rows")


def populate_dim_date(engine: Engine) -> None:
    with engine.begin() as conn:
        bounds = conn.execute(
            text(
                """
                SELECT
                    LEAST(MIN(failed_at)::date, MIN(flight_date)) AS min_date,
                    GREATEST(MAX(repaired_at)::date, MAX(flight_date)) AS max_date
                FROM staging.stg_maintenance_event, staging.stg_flight_hours
                """
            )
        ).one()
        start, end = bounds.min_date, bounds.max_date

    dates = pd.date_range(start, end, freq="D")
    dim_date = pd.DataFrame(
        {
            "date_key": [int(d.strftime("%Y%m%d")) for d in dates],
            "full_date": dates.date,
            "year": dates.year,
            "quarter": dates.quarter,
            "month": dates.month,
            "month_name": dates.strftime("%B"),
            "day": dates.day,
            "day_of_week": dates.dayofweek,
            "is_weekend": dates.dayofweek >= 5,
        }
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE warehouse.dim_date CASCADE"))
        dim_date.to_sql("dim_date", conn, schema="warehouse", if_exists="append", index=False)
    print(f"warehouse.dim_date: {len(dim_date):>7,} rows ({start} .. {end})")


UPSERT_DIMENSIONS_SQL = """
INSERT INTO warehouse.dim_aircraft (tail_number, aircraft_type, manufacturer, in_service_date, fleet_status)
SELECT tail_number, aircraft_type, manufacturer, in_service_date, fleet_status FROM staging.stg_aircraft
ON CONFLICT (tail_number) DO UPDATE SET
    aircraft_type = EXCLUDED.aircraft_type,
    manufacturer = EXCLUDED.manufacturer,
    in_service_date = EXCLUDED.in_service_date,
    fleet_status = EXCLUDED.fleet_status;

INSERT INTO warehouse.dim_component (component_code, ata_chapter, component_name, component_category, criticality, unit_cost, hourly_downtime_cost)
SELECT component_code, ata_chapter, component_name, component_category, criticality, unit_cost, hourly_downtime_cost FROM staging.stg_component
ON CONFLICT (component_code) DO UPDATE SET
    ata_chapter = EXCLUDED.ata_chapter,
    component_name = EXCLUDED.component_name,
    component_category = EXCLUDED.component_category,
    criticality = EXCLUDED.criticality,
    unit_cost = EXCLUDED.unit_cost,
    hourly_downtime_cost = EXCLUDED.hourly_downtime_cost;

INSERT INTO warehouse.dim_base (base_code, base_name, region, country)
SELECT base_code, base_name, region, country FROM staging.stg_base
ON CONFLICT (base_code) DO UPDATE SET
    base_name = EXCLUDED.base_name,
    region = EXCLUDED.region,
    country = EXCLUDED.country;
"""

LOAD_FACT_MAINTENANCE_EVENT_SQL = """
TRUNCATE TABLE warehouse.fact_maintenance_event;

INSERT INTO warehouse.fact_maintenance_event
    (event_id, aircraft_key, component_key, base_key, date_key, event_type,
     failure_mode, severity, flight_hours_at_failure, failed_at, repaired_at,
     labor_cost, parts_cost)
SELECT
    s.event_id,
    a.aircraft_key,
    c.component_key,
    b.base_key,
    (EXTRACT(YEAR FROM s.failed_at) * 10000
        + EXTRACT(MONTH FROM s.failed_at) * 100
        + EXTRACT(DAY FROM s.failed_at))::int AS date_key,
    s.event_type,
    s.failure_mode,
    s.severity,
    s.flight_hours_at_failure,
    s.failed_at,
    s.repaired_at,
    s.labor_cost,
    s.parts_cost
FROM staging.stg_maintenance_event s
JOIN warehouse.dim_aircraft a  ON a.tail_number = s.tail_number
JOIN warehouse.dim_component c ON c.component_code = s.component_code
JOIN warehouse.dim_base b      ON b.base_code = s.base_code;
"""

LOAD_FACT_FLIGHT_HOURS_SQL = """
TRUNCATE TABLE warehouse.fact_flight_hours;

INSERT INTO warehouse.fact_flight_hours (aircraft_key, date_key, flight_hours, flight_cycles)
SELECT
    a.aircraft_key,
    (EXTRACT(YEAR FROM s.flight_date) * 10000
        + EXTRACT(MONTH FROM s.flight_date) * 100
        + EXTRACT(DAY FROM s.flight_date))::int AS date_key,
    s.flight_hours,
    s.flight_cycles
FROM staging.stg_flight_hours s
JOIN warehouse.dim_aircraft a ON a.tail_number = s.tail_number;
"""


def upsert_dimensions(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(UPSERT_DIMENSIONS_SQL))
    print("warehouse dimensions upserted (aircraft, component, base)")


def load_facts(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(LOAD_FACT_MAINTENANCE_EVENT_SQL))
        conn.execute(text(LOAD_FACT_FLIGHT_HOURS_SQL))
        n_events = conn.execute(text("SELECT COUNT(*) FROM warehouse.fact_maintenance_event")).scalar()
        n_hours = conn.execute(text("SELECT COUNT(*) FROM warehouse.fact_flight_hours")).scalar()
    print(f"warehouse.fact_maintenance_event: {n_events:>7,} rows")
    print(f"warehouse.fact_flight_hours:      {n_hours:>7,} rows")


def run(data_dir: Path = DATA_DIR) -> None:
    engine = get_engine()
    load_staging(engine, data_dir)
    populate_dim_date(engine)
    upsert_dimensions(engine)
    load_facts(engine)


if __name__ == "__main__":
    run()
