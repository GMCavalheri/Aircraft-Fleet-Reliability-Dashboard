-- =====================================================================
-- Aircraft Fleet Reliability Dashboard
-- Phase 1: Star-schema data model
--
-- Grain:
--   fact_maintenance_event : one row per maintenance/failure/replacement
--                             event on one component of one aircraft
--   fact_flight_hours      : one row per (aircraft, day) of operation
-- =====================================================================

-- ---------------------------------------------------------------------
-- STAGING (raw landing zone for the ETL, mirrors the generator's CSVs)
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.stg_aircraft (
    tail_number       TEXT PRIMARY KEY,
    aircraft_type     TEXT NOT NULL,
    manufacturer      TEXT NOT NULL,
    in_service_date   DATE NOT NULL,
    fleet_status      TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS staging.stg_component (
    component_code    TEXT PRIMARY KEY,
    ata_chapter        TEXT NOT NULL,
    component_name     TEXT NOT NULL,
    component_category TEXT NOT NULL,
    criticality         TEXT NOT NULL,
    unit_cost            NUMERIC(12,2) NOT NULL,
    hourly_downtime_cost NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.stg_base (
    base_code    TEXT PRIMARY KEY,
    base_name    TEXT NOT NULL,
    region       TEXT NOT NULL,
    country      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.stg_maintenance_event (
    event_id                  BIGINT PRIMARY KEY,
    tail_number                TEXT NOT NULL,
    component_code             TEXT NOT NULL,
    base_code                  TEXT NOT NULL,
    event_type                 TEXT NOT NULL,   -- failure | scheduled | replacement
    failure_mode                TEXT,
    severity                    TEXT,
    flight_hours_at_failure     NUMERIC(12,2),
    failed_at                   TIMESTAMP NOT NULL,
    repaired_at                 TIMESTAMP NOT NULL,
    labor_cost                  NUMERIC(12,2) NOT NULL DEFAULT 0,
    parts_cost                  NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS staging.stg_flight_hours (
    tail_number   TEXT NOT NULL,
    flight_date   DATE NOT NULL,
    flight_hours  NUMERIC(6,2) NOT NULL,
    flight_cycles INTEGER NOT NULL,
    PRIMARY KEY (tail_number, flight_date)
);

-- ---------------------------------------------------------------------
-- WAREHOUSE (star schema): dimensions
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS warehouse;

CREATE TABLE IF NOT EXISTS warehouse.dim_aircraft (
    aircraft_key     SERIAL PRIMARY KEY,
    tail_number      TEXT NOT NULL UNIQUE,
    aircraft_type    TEXT NOT NULL,
    manufacturer     TEXT NOT NULL,
    in_service_date  DATE NOT NULL,
    fleet_status     TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS warehouse.dim_component (
    component_key         SERIAL PRIMARY KEY,
    component_code        TEXT NOT NULL UNIQUE,
    ata_chapter            TEXT NOT NULL,
    component_name         TEXT NOT NULL,
    component_category     TEXT NOT NULL,
    criticality             TEXT NOT NULL CHECK (criticality IN ('low','medium','high','critical')),
    unit_cost                NUMERIC(12,2) NOT NULL CHECK (unit_cost >= 0),
    hourly_downtime_cost     NUMERIC(12,2) NOT NULL CHECK (hourly_downtime_cost >= 0)
);

CREATE TABLE IF NOT EXISTS warehouse.dim_base (
    base_key     SERIAL PRIMARY KEY,
    base_code    TEXT NOT NULL UNIQUE,
    base_name    TEXT NOT NULL,
    region       TEXT NOT NULL,
    country      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key      INTEGER PRIMARY KEY,       -- YYYYMMDD
    full_date     DATE NOT NULL UNIQUE,
    year          SMALLINT NOT NULL,
    quarter       SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    month_name    TEXT NOT NULL,
    day           SMALLINT NOT NULL,
    day_of_week   SMALLINT NOT NULL,          -- 0=Monday .. 6=Sunday
    is_weekend    BOOLEAN NOT NULL
);

-- ---------------------------------------------------------------------
-- WAREHOUSE: facts
-- ---------------------------------------------------------------------

-- Fact: one row per maintenance/failure/replacement event.
CREATE TABLE IF NOT EXISTS warehouse.fact_maintenance_event (
    event_id                  BIGINT PRIMARY KEY,
    aircraft_key               INTEGER NOT NULL REFERENCES warehouse.dim_aircraft(aircraft_key),
    component_key               INTEGER NOT NULL REFERENCES warehouse.dim_component(component_key),
    base_key                    INTEGER NOT NULL REFERENCES warehouse.dim_base(base_key),
    date_key                    INTEGER NOT NULL REFERENCES warehouse.dim_date(date_key),
    event_type                  TEXT NOT NULL CHECK (event_type IN ('failure','scheduled','replacement')),
    failure_mode                 TEXT,
    severity                     TEXT CHECK (severity IN ('minor','major','critical') OR severity IS NULL),
    flight_hours_at_failure      NUMERIC(12,2),
    failed_at                    TIMESTAMP NOT NULL,
    repaired_at                  TIMESTAMP NOT NULL,
    repair_hours                 NUMERIC(10,2) GENERATED ALWAYS AS
                                    (EXTRACT(EPOCH FROM (repaired_at - failed_at)) / 3600.0) STORED,
    labor_cost                   NUMERIC(12,2) NOT NULL DEFAULT 0,
    parts_cost                   NUMERIC(12,2) NOT NULL DEFAULT 0,
    downtime_cost                NUMERIC(14,2) GENERATED ALWAYS AS
                                    (labor_cost + parts_cost) STORED,
    CONSTRAINT chk_repair_after_failure CHECK (repaired_at >= failed_at)
);

CREATE INDEX IF NOT EXISTS idx_fme_aircraft   ON warehouse.fact_maintenance_event(aircraft_key);
CREATE INDEX IF NOT EXISTS idx_fme_component  ON warehouse.fact_maintenance_event(component_key);
CREATE INDEX IF NOT EXISTS idx_fme_date       ON warehouse.fact_maintenance_event(date_key);
CREATE INDEX IF NOT EXISTS idx_fme_event_type ON warehouse.fact_maintenance_event(event_type);

-- Fact: daily operating hours per aircraft (denominator for MTBF).
CREATE TABLE IF NOT EXISTS warehouse.fact_flight_hours (
    aircraft_key   INTEGER NOT NULL REFERENCES warehouse.dim_aircraft(aircraft_key),
    date_key       INTEGER NOT NULL REFERENCES warehouse.dim_date(date_key),
    flight_hours   NUMERIC(6,2) NOT NULL CHECK (flight_hours >= 0),
    flight_cycles  INTEGER NOT NULL CHECK (flight_cycles >= 0),
    PRIMARY KEY (aircraft_key, date_key)
);

CREATE INDEX IF NOT EXISTS idx_ffh_date ON warehouse.fact_flight_hours(date_key);
