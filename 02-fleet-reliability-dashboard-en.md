# Aircraft Fleet Reliability Dashboard

## Overview
A data engineering and visualization project that simulates a reliability monitoring system for an aircraft fleet, featuring classic maintenance metrics (MTBF, MTTR, availability) and analytical queries over historical failure and maintenance data.

## Objective
Build a data pipeline (ETL → data model → dashboard) to monitor and compare the performance of aircraft, components, and the fleet as a whole — directly addressing the job's responsibility of "developing information tools, algorithms, dashboards, and queries."

## Why This Project
- Covers the part of the job least addressed by the other projects: dashboards, queries, and information tools for maintenance/operations teams.
- Reinforces SQL and data modeling skills, complementary to the ML-focused projects.
- An easy artifact to demonstrate in an interview (visual, interactive, straight to the point).

## Data
Since real airline fleet data isn't public, there are two options:
1. **Realistic synthetic data**: generate a simulated dataset of maintenance events (failures, repairs, component replacements) per aircraft/component, with plausible statistical distributions (e.g., failures following a Weibull distribution, common in reliability engineering).
2. **Supplement with real public data**: the NTSB Aviation Accident Database or ASRS (Aviation Safety Reporting System) to add realistic context to failure categories and severity.

## Tech Stack
- Python (data generation/processing), Pandas
- PostgreSQL (relational data model)
- SQL (analytical queries)
- Streamlit or Power BI/Metabase for the dashboard
- Airflow (optional) to simulate periodic data refreshes

## Reliability Metrics to Implement
- **MTBF** (Mean Time Between Failures) by component and by aircraft
- **MTTR** (Mean Time To Repair)
- **Availability** (Availability = MTBF / (MTBF + MTTR))
- **Failure rate** over time (bathtub curve / Weibull analysis)
- **Failure Pareto** — which components account for the most occurrences
- **Estimated downtime cost** by failure type

## Solution Architecture
1. Generation/ingestion of maintenance event data (staging)
2. Modeling in a relational schema (fact: failure/repair events; dimensions: aircraft, component, maintenance base, time)
3. SQL query layer to compute reliability metrics
4. Interactive dashboard with filters by aircraft, component, and period

## Execution Plan
- [x] **Phase 1 — Data modeling**: design a fact/dimension schema for maintenance and failure events.
- [x] **Phase 2 — Synthetic data generation**: simulate a realistic failure history (statistical reliability distributions).
- [x] **Phase 3 — ETL**: load pipeline into PostgreSQL, with data quality tests.
- [x] **Phase 4 — Analytical queries**: implement the metrics (MTBF, MTTR, availability, Pareto) in SQL.
- [x] **Phase 5 — Dashboard**: build interactive visualizations (Streamlit/Power BI) with filters and drill-down.
- [x] **Phase 6 — Documentation**: README explaining the data model, the metrics, and how to interpret them.

## Deliverables
- Repository with data model, ETL scripts, and documented queries
- Interactive Streamlit dashboard running locally against the Dockerized Postgres warehouse
- Documentation of the reliability metrics and how they were calculated

## Portfolio Differentiators
- Demonstrates data modeling and analytical SQL skills, not just ML — a core skill that is often underestimated in reliability engineering roles.
- Reliability metrics (MTBF/MTTR/Weibull) are domain-specific technical vocabulary, signaling domain knowledge during the interview.

## Possible Extensions
- Add automatic alerts when a component exceeds a failure-rate threshold
- Integrate with the RUL prediction project (show predicted RUL alongside historical metrics)
