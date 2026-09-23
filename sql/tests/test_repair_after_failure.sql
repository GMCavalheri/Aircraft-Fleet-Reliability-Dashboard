-- Every event's repair must finish at or after it started.
SELECT event_id, failed_at, repaired_at
FROM warehouse.fact_maintenance_event
WHERE repaired_at < failed_at;
