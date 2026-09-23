# Reliability metrics: definitions, formulas, and how to read them

All metrics are defined once, as SQL views in
[sql/02_views_metrics.sql](../sql/02_views_metrics.sql), and re-implemented
in [app/metrics.py](../app/metrics.py) with identical formulas so the
dashboard's filters (aircraft, component, base, period) apply without
drifting from the validated SQL definitions.

## MTBF -- Mean Time Between Failures

$$
\text{MTBF} = \frac{\text{total operating hours}}{\text{failure count}}
$$

- "Operating hours" = flight hours from `fact_flight_hours`, **not**
  calendar time -- flight hours is the physically correct exposure unit
  for wear-out failures.
- "Failure count" only counts `event_type = 'failure'` rows. Preventive
  `replacement` events and routine `scheduled` inspections are excluded
  on purpose: counting them would understate how reliable the part
  actually is, since they are not failures.
- By component: fleet-wide operating hours / that component's failure
  count. By aircraft: that aircraft's own operating hours / its failure
  count across all components.

## MTTR -- Mean Time To Repair

$$
\text{MTTR} = \text{mean}(\text{repair\_hours}) \quad \text{over failure events}
$$

`repair_hours` is a generated column (`repaired_at - failed_at` in
hours) computed by Postgres at write time, not recomputed per query.

## Availability

$$
\text{Availability} = \frac{\text{MTBF}}{\text{MTBF} + \text{MTTR}}
$$

**Caveat, stated explicitly rather than hidden**: this mixes two
different time bases. MTBF is in *flight hours*; MTTR is in *calendar
hours*. The textbook formula implicitly treats an aircraft as "up" only
while flying, which pushes computed availability very close to 100%
(MTTR in hours is tiny next to MTBF in thousands of flight hours). A
production reliability system would express both in the same time
basis (e.g. calendar-time exposure) to get a number that genuinely
means "% of calendar time available." Treat this project's availability
figures as directionally useful for comparing components, not as a
literal operational-availability percentage.

## Failure rate over time / bathtub curve

Monthly failure counts per component category
(`v_failure_rate_monthly`), and per-component Weibull hazard curves
fitted live on the dashboard's Weibull page. The shape parameter β
tells you which regime a component is in:

| β | Hazard | Interpretation |
|---|---|---|
| < 1 | decreasing | early-life / infant mortality -- a burn-in or manufacturing issue |
| ≈ 1 | flat | random, memoryless failures (Weibull ≡ Exponential here) |
| > 1 | increasing | wear-out -- age-based preventive replacement helps |

## Failure Pareto

Components ranked by failure count with a running cumulative
percentage, computed with one window function:

```sql
SUM(failure_count) OVER (ORDER BY failure_count DESC)
    / SUM(failure_count) OVER ()
```

Answers "which few components cause most of the failures" -- in this
project's generated data, 5 of 15 components already account for over
half of all failures.

## Estimated downtime cost

Two cost figures are kept **separate**, because they represent
different things and summing them without labeling would hide which
one actually drives the total:

- `labor_and_parts_cost` -- what was actually spent (`fact.labor_cost +
  fact.parts_cost`), i.e. the repair invoice.
- `estimated_downtime_cost` -- `repair_hours x
  dim_component.hourly_downtime_cost`, the aircraft's estimated lost
  operational value while grounded. This is a modeling *assumption*
  (a per-component hourly rate set in the synthetic data generator),
  not an observed cost -- treat it as illustrative, not a real airline's
  figures.

`total_estimated_cost` is the sum of the two, and is what the Overview
and Components pages rank by.

## Data source for failure-category and severity weights

[public_data.py](../src/fleet_reliability/public_data.py) documents
exactly which numbers used to bias the synthetic failure mix are cited
from a published NASA/NTSB study of System/Component Failure or
Malfunction (SCFM) accidents (48% engine/fuel, 31% landing
gear/hydraulics) versus which are this project's own reasonable
assumption for the remainder, which is not broken out at that
resolution in the public summary.
