-- Costs and hours should never be negative.
SELECT event_id, labor_cost, parts_cost
FROM warehouse.fact_maintenance_event
WHERE labor_cost < 0 OR parts_cost < 0

UNION ALL

SELECT NULL, NULL, NULL
WHERE EXISTS (
    SELECT 1 FROM warehouse.fact_flight_hours
    WHERE flight_hours < 0 OR flight_cycles < 0
);
