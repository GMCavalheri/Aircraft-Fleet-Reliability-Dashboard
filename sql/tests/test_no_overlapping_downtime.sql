-- A single component instance cannot be mid-repair on two events at once:
-- one (aircraft, component) slot should never show overlapping downtime
-- windows. (Different components on the same aircraft CAN overlap -- two
-- independent parts can legitimately be broken at the same time -- so the
-- check is scoped per component, not per aircraft.) Uses LAG() to compare
-- each event to the previous one for that slot, ordered by start time.
WITH ordered AS (
    SELECT
        event_id,
        aircraft_key,
        component_key,
        failed_at,
        repaired_at,
        LAG(repaired_at) OVER (PARTITION BY aircraft_key, component_key ORDER BY failed_at) AS prev_repaired_at,
        LAG(event_id) OVER (PARTITION BY aircraft_key, component_key ORDER BY failed_at) AS prev_event_id
    FROM warehouse.fact_maintenance_event
)
SELECT event_id, prev_event_id, aircraft_key, component_key, failed_at, prev_repaired_at
FROM ordered
WHERE prev_repaired_at IS NOT NULL
  AND failed_at < prev_repaired_at;
