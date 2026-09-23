# Aircraft fleet reliability dashboard

A data engineering and visualization project simulating a reliability
monitoring system for an aircraft fleet: a Weibull-based synthetic
maintenance history, a Postgres star schema, a validated SQL metrics
layer, and an interactive Streamlit dashboard covering the classic
reliability metrics -- MTBF, MTTR, availability, failure Pareto,
Weibull hazard analysis, and estimated downtime cost.

## Architecture

```
generate.py --> CSVs --> etl.py --> staging schema --> warehouse star schema
                                                              |
                                                    sql/02_views_metrics.sql
                                                              |
                                                     Streamlit dashboard (app/)
```

- **Python + pandas + NumPy** -- synthetic data generation (Weibull
  renewal process per aircraft/component).
- **PostgreSQL** -- star-schema warehouse, one `staging` and one
  `warehouse` schema.
- **SQL** -- all reliability metrics defined as views, validated
  directly against Postgres before the dashboard ever reads them.
- **Streamlit + Plotly** -- interactive dashboard with filters by
  aircraft type, component, maintenance base, and period.
- **scipy** -- Weibull maximum-likelihood fit, shown live against the
  synthetic data's true generating parameters.

See [docs/data_model.md](docs/data_model.md) for the schema and
[docs/metrics.md](docs/metrics.md) for every metric's formula, unit,
and documented assumptions/caveats.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

docker compose up -d
cp .env.example .env   # local Postgres on port 5433

docker compose exec -T postgres psql -U fleet -d fleet_reliability < sql/01_schema.sql
docker compose exec -T postgres psql -U fleet -d fleet_reliability < sql/02_views_metrics.sql

.venv/bin/python -m fleet_reliability.generate   # writes CSVs to data/
.venv/bin/python -m fleet_reliability.etl        # loads staging -> warehouse
.venv/bin/python -m fleet_reliability.quality    # data-quality gate, exits non-zero on failure

.venv/bin/pytest                                 # generator + integrity tests

.venv/bin/streamlit run app/streamlit_app.py
```

## Project layout

```
sql/01_schema.sql          star-schema DDL (staging + warehouse)
sql/02_views_metrics.sql   MTBF, MTTR, availability, Pareto, cost, Weibull input
sql/tests/*.sql            data-quality checks (each: rows returned = violations)
src/fleet_reliability/
  generate.py               Weibull-based synthetic maintenance history
  public_data.py            NTSB/ASRS-grounded failure-category weights
  etl.py                    staging -> warehouse load
  quality.py                runs sql/tests/*.sql, exits non-zero on failure
  db.py                     shared DATABASE_URL / engine
app/
  streamlit_app.py           Overview: KPIs, monthly trend, cost by category
  pages/1_Components.py      Failure Pareto + MTBF/MTTR/availability table
  pages/2_Aircraft.py        MTBF by aircraft + per-tail event drill-down
  pages/3_Weibull.py         live Weibull fit vs. the generator's true parameters
  data.py, metrics.py, filters.py, db.py
tests/test_generate.py     determinism, FK integrity, Weibull recovery sanity check
docs/data_model.md          schema, grain, ERD, documented simplifications
docs/metrics.md             every metric's formula and caveats
```

## Deployment

The dashboard is designed to run unmodified against either the local
Docker Postgres or a hosted one:

1. **Database**: create a free Postgres instance (e.g.
   [Neon](https://neon.tech) or [Supabase](https://supabase.com)),
   apply `sql/01_schema.sql` and `sql/02_views_metrics.sql`, then run
   `fleet_reliability.etl` with `DATABASE_URL` pointed at it.
2. **App**: push this repo to GitHub and deploy `app/streamlit_app.py`
   on [Streamlit Cloud](https://streamlit.io/cloud). Set `DATABASE_URL`
   in the app's Secrets (`st.secrets`) -- `app/db.py` already prefers
   `st.secrets` over the `.env` file used locally, so no code change is
   needed between environments.

The generated dataset is small by design (a few MB total, see
[generate.py](src/fleet_reliability/generate.py)) so it fits
comfortably within a free-tier hosted database.

## Reliability metrics implemented

- MTBF by component and by aircraft
- MTTR
- Availability (MTBF / (MTBF + MTTR), with the flight-hours-vs-
  calendar-hours caveat documented in [docs/metrics.md](docs/metrics.md))
- Failure rate over time / Weibull hazard analysis (bathtub curve)
- Failure Pareto by component
- Estimated downtime cost by failure category

## Possible extensions

- Automatic alerts when a component's failure rate crosses a threshold.
- Airflow DAG to simulate periodic data refreshes.
- Integration with a remaining-useful-life (RUL) prediction model,
  showing predicted RUL alongside the historical metrics.
