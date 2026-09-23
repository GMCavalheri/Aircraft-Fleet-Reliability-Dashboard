-- Every fact row's dimension keys must resolve to an existing dimension row.
-- (Belt-and-braces: the FK constraints in the schema already guarantee this
-- for warehouse tables; this check is the one that would catch a problem if
-- the ETL ever loaded facts through a path that bypasses those constraints.)
SELECT f.event_id, 'aircraft_key' AS missing_dimension
FROM warehouse.fact_maintenance_event f
LEFT JOIN warehouse.dim_aircraft a ON a.aircraft_key = f.aircraft_key
WHERE a.aircraft_key IS NULL

UNION ALL

SELECT f.event_id, 'component_key'
FROM warehouse.fact_maintenance_event f
LEFT JOIN warehouse.dim_component c ON c.component_key = f.component_key
WHERE c.component_key IS NULL

UNION ALL

SELECT f.event_id, 'base_key'
FROM warehouse.fact_maintenance_event f
LEFT JOIN warehouse.dim_base b ON b.base_key = f.base_key
WHERE b.base_key IS NULL

UNION ALL

SELECT f.event_id, 'date_key'
FROM warehouse.fact_maintenance_event f
LEFT JOIN warehouse.dim_date d ON d.date_key = f.date_key
WHERE d.date_key IS NULL;
