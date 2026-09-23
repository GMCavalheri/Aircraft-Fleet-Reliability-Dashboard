-- =====================================================================
-- Phase 4: analytical SQL layer -- reliability metrics
--
-- Simplification (documented): every aircraft carries all 15 component
-- types continuously from its in-service date, and components are never
-- removed without a logged event. So "operating hours exposed to a
-- given component" is simply the aircraft's own flight hours over the
-- observation window -- we don't need a separate component-installation
-- history table. A fleet with partial retrofits would need one.
-- =====================================================================

CREATE OR REPLACE VIEW warehouse.v_fleet_exposure_hours AS
SELECT SUM(flight_hours) AS total_flight_hours
FROM warehouse.fact_flight_hours;

CREATE OR REPLACE VIEW warehouse.v_aircraft_exposure_hours AS
SELECT aircraft_key, SUM(flight_hours) AS flight_hours
FROM warehouse.fact_flight_hours
GROUP BY aircraft_key;

-- MTBF by component = fleet-wide operating hours / failure count.
-- ("failure" events only -- preventive replacements and inspections are
-- not failures and would understate true reliability if counted.)
CREATE OR REPLACE VIEW warehouse.v_mtbf_by_component AS
SELECT
    c.component_key,
    c.component_code,
    c.component_name,
    c.component_category,
    COUNT(*) FILTER (WHERE f.event_type = 'failure') AS failure_count,
    fe.total_flight_hours,
    fe.total_flight_hours
        / NULLIF(COUNT(*) FILTER (WHERE f.event_type = 'failure'), 0) AS mtbf_hours
FROM warehouse.dim_component c
CROSS JOIN warehouse.v_fleet_exposure_hours fe
LEFT JOIN warehouse.fact_maintenance_event f ON f.component_key = c.component_key
GROUP BY c.component_key, c.component_code, c.component_name, c.component_category,
         fe.total_flight_hours;

-- MTBF by aircraft = that aircraft's own operating hours / its failure
-- count across all components.
CREATE OR REPLACE VIEW warehouse.v_mtbf_by_aircraft AS
SELECT
    a.aircraft_key,
    a.tail_number,
    a.aircraft_type,
    COUNT(*) FILTER (WHERE f.event_type = 'failure') AS failure_count,
    ae.flight_hours,
    ae.flight_hours
        / NULLIF(COUNT(*) FILTER (WHERE f.event_type = 'failure'), 0) AS mtbf_hours
FROM warehouse.dim_aircraft a
JOIN warehouse.v_aircraft_exposure_hours ae ON ae.aircraft_key = a.aircraft_key
LEFT JOIN warehouse.fact_maintenance_event f ON f.aircraft_key = a.aircraft_key
GROUP BY a.aircraft_key, a.tail_number, a.aircraft_type, ae.flight_hours;

-- MTTR by component: mean repair duration of failure events only.
CREATE OR REPLACE VIEW warehouse.v_mttr_by_component AS
SELECT
    component_key,
    AVG(repair_hours) AS mttr_hours,
    COUNT(*) AS failure_count
FROM warehouse.fact_maintenance_event
WHERE event_type = 'failure'
GROUP BY component_key;

-- Availability = MTBF / (MTBF + MTTR).
CREATE OR REPLACE VIEW warehouse.v_availability_by_component AS
SELECT
    m.component_key,
    m.component_code,
    m.component_name,
    m.component_category,
    m.mtbf_hours,
    t.mttr_hours,
    m.mtbf_hours / NULLIF(m.mtbf_hours + t.mttr_hours, 0) AS availability
FROM warehouse.v_mtbf_by_component m
LEFT JOIN warehouse.v_mttr_by_component t ON t.component_key = m.component_key;

-- Monthly failure counts per component -- input to the bathtub-curve /
-- failure-rate-over-time chart.
CREATE OR REPLACE VIEW warehouse.v_failure_rate_monthly AS
SELECT
    date_trunc('month', f.failed_at)::date AS month,
    c.component_key,
    c.component_code,
    c.component_category,
    COUNT(*) AS failure_count
FROM warehouse.fact_maintenance_event f
JOIN warehouse.dim_component c ON c.component_key = f.component_key
WHERE f.event_type = 'failure'
GROUP BY 1, c.component_key, c.component_code, c.component_category;

-- Failure Pareto: components ranked by failure count, with a running
-- cumulative percentage -- the classic "which 20% of components cause
-- 80% of the failures" view.
CREATE OR REPLACE VIEW warehouse.v_failure_pareto AS
WITH counts AS (
    SELECT
        c.component_key,
        c.component_code,
        c.component_name,
        COUNT(*) AS failure_count
    FROM warehouse.fact_maintenance_event f
    JOIN warehouse.dim_component c ON c.component_key = f.component_key
    WHERE f.event_type = 'failure'
    GROUP BY c.component_key, c.component_code, c.component_name
)
SELECT
    component_key,
    component_code,
    component_name,
    failure_count,
    SUM(failure_count) OVER (ORDER BY failure_count DESC, component_code) AS cumulative_failures,
    ROUND(
        100.0 * SUM(failure_count) OVER (ORDER BY failure_count DESC, component_code)
        / SUM(failure_count) OVER (),
        1
    ) AS cumulative_pct
FROM counts
ORDER BY failure_count DESC;

-- Estimated cost of failures by component category. Two cost components,
-- kept separate on purpose:
--   labor_and_parts_cost      = what was actually spent fixing it
--                                (fact.labor_cost + fact.parts_cost)
--   estimated_downtime_cost   = the aircraft's lost operational value
--                                while grounded (repair_hours x the
--                                component's dim.hourly_downtime_cost)
CREATE OR REPLACE VIEW warehouse.v_downtime_cost_by_category AS
SELECT
    c.component_category,
    COUNT(*) AS failure_count,
    SUM(f.repair_hours) AS total_repair_hours,
    SUM(f.downtime_cost) AS labor_and_parts_cost,
    SUM(f.repair_hours * c.hourly_downtime_cost) AS estimated_downtime_cost,
    SUM(f.downtime_cost) + SUM(f.repair_hours * c.hourly_downtime_cost) AS total_estimated_cost
FROM warehouse.fact_maintenance_event f
JOIN warehouse.dim_component c ON c.component_key = f.component_key
WHERE f.event_type = 'failure'
GROUP BY c.component_category
ORDER BY total_estimated_cost DESC;

-- Per-instance time between failures/replacements, in flight hours --
-- feeds the Python-side Weibull fit (Phase 5). flight_hours_at_failure
-- is the aircraft's cumulative flight hours at the event; the component
-- clock resets after every failure/replacement, so the gap since the
-- previous event on that same (aircraft, component) slot is exactly the
-- component's own time-to-failure.
CREATE OR REPLACE VIEW warehouse.v_time_between_failures AS
SELECT
    f.event_id,
    f.aircraft_key,
    f.component_key,
    c.component_code,
    f.failed_at,
    f.event_type,
    f.flight_hours_at_failure
        - COALESCE(
            LAG(f.flight_hours_at_failure) OVER (
                PARTITION BY f.aircraft_key, f.component_key ORDER BY f.failed_at
            ),
            0
          ) AS hours_since_last_event
FROM warehouse.fact_maintenance_event f
JOIN warehouse.dim_component c ON c.component_key = f.component_key
WHERE f.event_type IN ('failure', 'replacement')
  AND f.flight_hours_at_failure IS NOT NULL;
