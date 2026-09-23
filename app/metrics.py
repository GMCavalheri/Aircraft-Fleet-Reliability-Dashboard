"""Reliability metrics computed in pandas on a (filtered) slice of the
event and flight-hours tables. Formulas are the same ones defined as
SQL views in sql/02_views_metrics.sql -- see that file and docs/metrics.md
for the definitions; this module just re-implements them so the
dashboard's filters (aircraft, component, base, date range) apply.
"""

from __future__ import annotations

import pandas as pd


def kpis(events: pd.DataFrame, flight_hours: pd.DataFrame) -> dict:
    total_hours = float(flight_hours["flight_hours"].sum())
    failures = events[events["event_type"] == "failure"]
    failure_count = len(failures)

    mtbf = total_hours / failure_count if failure_count else float("nan")
    mttr = float(failures["repair_hours"].mean()) if failure_count else float("nan")
    availability = mtbf / (mtbf + mttr) if failure_count and (mtbf + mttr) else float("nan")

    labor_parts_cost = float(failures["downtime_cost"].sum())
    estimated_downtime_cost = float((failures["repair_hours"] * failures["hourly_downtime_cost"]).sum())

    return {
        "total_flight_hours": total_hours,
        "failure_count": failure_count,
        "mtbf_hours": mtbf,
        "mttr_hours": mttr,
        "availability": availability,
        "labor_parts_cost": labor_parts_cost,
        "estimated_downtime_cost": estimated_downtime_cost,
        "total_cost": labor_parts_cost + estimated_downtime_cost,
    }


def mtbf_by_component(events: pd.DataFrame, flight_hours: pd.DataFrame) -> pd.DataFrame:
    total_hours = float(flight_hours["flight_hours"].sum())
    failures = events[events["event_type"] == "failure"]
    counts = failures.groupby(["component_code", "component_name", "component_category"]).size()
    counts.name = "failure_count"
    out = counts.reset_index()
    out["mtbf_hours"] = total_hours / out["failure_count"]
    return out.sort_values("mtbf_hours")


def mttr_by_component(events: pd.DataFrame) -> pd.DataFrame:
    failures = events[events["event_type"] == "failure"]
    out = failures.groupby("component_code")["repair_hours"].mean().reset_index()
    out.columns = ["component_code", "mttr_hours"]
    return out


def availability_by_component(events: pd.DataFrame, flight_hours: pd.DataFrame) -> pd.DataFrame:
    m = mtbf_by_component(events, flight_hours)
    t = mttr_by_component(events)
    out = m.merge(t, on="component_code", how="left")
    out["availability"] = out["mtbf_hours"] / (out["mtbf_hours"] + out["mttr_hours"])
    return out


def mtbf_by_aircraft(events: pd.DataFrame, flight_hours: pd.DataFrame) -> pd.DataFrame:
    hours_by_tail = flight_hours.groupby(["tail_number", "aircraft_type"])["flight_hours"].sum()
    failures = events[events["event_type"] == "failure"]
    counts = failures.groupby("tail_number").size()
    counts.name = "failure_count"
    out = hours_by_tail.reset_index().merge(counts.reset_index(), on="tail_number", how="left")
    out["failure_count"] = out["failure_count"].fillna(0).astype(int)
    out["mtbf_hours"] = out["flight_hours"] / out["failure_count"].replace(0, pd.NA)
    return out.sort_values("mtbf_hours")


def failure_pareto(events: pd.DataFrame) -> pd.DataFrame:
    failures = events[events["event_type"] == "failure"]
    counts = failures.groupby(["component_code", "component_name"]).size()
    counts.name = "failure_count"
    out = counts.reset_index().sort_values("failure_count", ascending=False)
    total = out["failure_count"].sum()
    out["cumulative_failures"] = out["failure_count"].cumsum()
    out["cumulative_pct"] = (100 * out["cumulative_failures"] / total).round(1)
    return out.reset_index(drop=True)


def monthly_failure_rate(events: pd.DataFrame) -> pd.DataFrame:
    failures = events[events["event_type"] == "failure"].copy()
    failures["month"] = failures["failed_at"].dt.to_period("M").dt.to_timestamp()
    out = failures.groupby(["month", "component_category"]).size().reset_index(name="failure_count")
    return out


def downtime_cost_by_category(events: pd.DataFrame) -> pd.DataFrame:
    failures = events[events["event_type"] == "failure"].copy()
    failures["estimated_downtime_cost"] = failures["repair_hours"] * failures["hourly_downtime_cost"]
    out = (
        failures.groupby("component_category")
        .agg(
            failure_count=("event_id", "count"),
            total_repair_hours=("repair_hours", "sum"),
            labor_and_parts_cost=("downtime_cost", "sum"),
            estimated_downtime_cost=("estimated_downtime_cost", "sum"),
        )
        .reset_index()
    )
    out["total_estimated_cost"] = out["labor_and_parts_cost"] + out["estimated_downtime_cost"]
    return out.sort_values("total_estimated_cost", ascending=False)
