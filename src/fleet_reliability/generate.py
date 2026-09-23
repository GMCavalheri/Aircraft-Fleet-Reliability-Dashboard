"""Synthetic maintenance-history generator for the fleet reliability project.

Simulates, per (aircraft, component) pair, a renewal process driven by a
Weibull time-to-failure distribution:

    Reliability:  R(t) = exp(-(t / eta) ** beta)
    Hazard rate:  h(t) = (beta / eta) * (t / eta) ** (beta - 1)

  - beta < 1  -> decreasing hazard  (infant mortality / early-life defects)
  - beta = 1  -> constant hazard    (random, memoryless failures; Weibull
                 reduces to the Exponential distribution)
  - beta > 1  -> increasing hazard  (wear-out)

Component "clocks" run in flight hours, not calendar time, because that is
the physically correct unit for wear-out. Calendar failure dates are found
by walking each aircraft's simulated daily flight-hours series.

Three event types are produced:
  - failure      unscheduled, drawn from the Weibull renewal process.
  - replacement  proactive/preventive swap of a life-limited critical part
                 before it reaches its Weibull-drawn failure time (i.e. a
                 maintenance program capping time-on-wing). Also resets
                 the component's clock.
  - scheduled    routine inspection on a fixed calendar cadence, short
                 downtime, does not reset the failure clock and is
                 excluded from MTBF (it is not a failure).

Reproducibility: everything is driven off a single seeded
numpy.random.Generator, so re-running this script produces byte-identical
output.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from fleet_reliability.public_data import SEVERITY_WEIGHTS_BY_CATEGORY

SEED = 42
START_DATE = dt.date(2020, 1, 1)
END_DATE = dt.date(2025, 12, 31)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SAMPLE_DIR = DATA_DIR / "sample"
SAMPLE_N_EVENTS = 300
SAMPLE_N_FLIGHT_ROWS = 500

LABOR_RATE_PER_HOUR = 150.0

AIRCRAFT_TYPES = [
    ("A320-200", "Airbus", 45),
    ("B737-800", "Boeing", 45),
    ("E190", "Embraer", 10),
]
N_AIRCRAFT = sum(share for _, _, share in AIRCRAFT_TYPES)  # 100 -> scaled below
FLEET_SIZE = 45  # keep the dataset small enough for a free-tier hosted DB

BASES = [
    ("GRU", "Sao Paulo Guarulhos MX Base", "South America", "Brazil"),
    ("MIA", "Miami MX Base", "North America", "USA"),
    ("LIS", "Lisbon MX Base", "Europe", "Portugal"),
    ("JNB", "Johannesburg MX Base", "Africa", "South Africa"),
]

# component_code, name, ata_chapter, category, criticality, unit_cost,
# hourly_downtime_cost, weibull_beta, weibull_eta_hours, mttr_mean_hours,
# replacement_interval_hours (None = no preventive program),
# failure_modes
COMPONENTS = [
    ("ENG-CORE", "Engine core module", "72", "engine_fuel", "critical",
     850_000, 4_500, 2.2, 18_000, 48, 20_000,
     ["blade wear", "bearing degradation", "overheat trip"]),
    ("FUEL-PUMP", "Fuel boost pump", "28", "engine_fuel", "high",
     12_000, 1_200, 1.3, 9_000, 6, None,
     ["seal leak", "motor burnout", "pressure loss"]),
    ("FUEL-CTRL", "Fuel control unit", "73", "engine_fuel", "high",
     35_000, 1_500, 1.1, 11_000, 10, None,
     ["sensor drift", "software fault", "connector corrosion"]),
    ("MLG-ACT", "Main landing gear actuator", "32", "landing_gear_hydraulics", "critical",
     60_000, 2_000, 1.8, 14_000, 20, 15_000,
     ["hydraulic leak", "actuator seizure", "fatigue crack"]),
    ("HYD-PUMP", "Hydraulic pump", "29", "landing_gear_hydraulics", "high",
     22_000, 1_300, 1.4, 8_000, 8, None,
     ["seal leak", "cavitation wear", "pressure loss"]),
    ("BRAKE-ASM", "Brake assembly", "32", "landing_gear_hydraulics", "high",
     15_000, 900, 1.6, 6_000, 5, None,
     ["lining wear", "overheat trip", "sensor fault"]),
    ("NLG-STRUT", "Nose landing gear strut", "32", "landing_gear_hydraulics", "medium",
     18_000, 1_000, 1.9, 16_000, 12, None,
     ["seal leak", "corrosion", "fatigue crack"]),
    ("FMC", "Flight management computer", "34", "avionics_electrical", "high",
     40_000, 1_800, 0.9, 20_000, 4, None,
     ["software fault", "power supply fault", "connector corrosion"]),
    ("GEN", "AC generator", "24", "avionics_electrical", "high",
     28_000, 1_400, 1.2, 13_000, 6, None,
     ["bearing wear", "winding short", "voltage regulation fault"]),
    ("BATT", "Main battery", "24", "avionics_electrical", "medium",
     6_000, 600, 1.5, 5_000, 3, None,
     ["capacity loss", "thermal runaway", "connector corrosion"]),
    ("AIL-ACT", "Aileron actuator", "27", "flight_controls", "high",
     25_000, 1_600, 1.7, 15_000, 10, None,
     ["hydraulic leak", "actuator seizure", "sensor fault"]),
    ("ELEV-TRIM", "Elevator trim motor", "27", "flight_controls", "medium",
     9_000, 800, 1.3, 10_000, 5, None,
     ["motor burnout", "gear wear", "sensor fault"]),
    ("CAB-PRESS", "Cabin pressure controller", "21", "structural_ecs_apu", "medium",
     11_000, 700, 1.1, 12_000, 4, None,
     ["sensor drift", "software fault", "valve sticking"]),
    ("APU-START", "APU starter motor", "49", "structural_ecs_apu", "medium",
     14_000, 900, 1.4, 9_000, 6, None,
     ["motor burnout", "bearing wear", "connector corrosion"]),
    ("WING-SENS", "Wing structural sensor", "53", "structural_ecs_apu", "low",
     4_000, 400, 1.0, 25_000, 2, None,
     ["sensor drift", "connector corrosion", "calibration fault"]),
]

CATEGORY_OF = {c[0]: c[3] for c in COMPONENTS}


def build_dimensions(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the aircraft, component, and base staging tables."""
    rows = []
    tail = 1
    for ac_type, manufacturer, share in AIRCRAFT_TYPES:
        n = max(1, round(FLEET_SIZE * share / N_AIRCRAFT))
        for _ in range(n):
            in_service = START_DATE + dt.timedelta(
                days=int(rng.integers(0, 365))
            )
            rows.append(
                {
                    "tail_number": f"PP-{tail:03d}",
                    "aircraft_type": ac_type,
                    "manufacturer": manufacturer,
                    "in_service_date": in_service,
                    "fleet_status": "active",
                }
            )
            tail += 1
    aircraft_df = pd.DataFrame(rows).head(FLEET_SIZE)

    component_df = pd.DataFrame(
        [
            {
                "component_code": c[0],
                "ata_chapter": c[2],
                "component_name": c[1],
                "component_category": c[3],
                "criticality": c[4],
                "unit_cost": c[5],
                "hourly_downtime_cost": c[6],
            }
            for c in COMPONENTS
        ]
    )

    base_df = pd.DataFrame(
        [
            {"base_code": code, "base_name": name, "region": region, "country": country}
            for code, name, region, country in BASES
        ]
    )
    return aircraft_df, component_df, base_df


def simulate_flight_hours(
    aircraft_df: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Simulate daily flight hours per aircraft; return the long table plus
    a per-tail cumulative-hours Series (indexed by date) used to convert
    Weibull hour-draws into calendar failure dates."""
    all_rows = []
    cumulative_by_tail: dict[str, pd.Series] = {}

    for _, ac in aircraft_df.iterrows():
        start = max(ac["in_service_date"], START_DATE)
        dates = pd.date_range(start, END_DATE, freq="D")
        mean_daily_hours = float(np.clip(rng.normal(7.0, 1.5), 3.0, 11.0))
        noise = rng.normal(0, 1.2, size=len(dates))
        ground_day = rng.random(len(dates)) < 0.04
        daily_hours = np.clip(mean_daily_hours + noise, 0, None)
        daily_hours[ground_day] = 0.0
        daily_hours = np.round(daily_hours, 2)
        flight_cycles = np.round(daily_hours / rng.uniform(1.2, 1.8), 0).astype(int)

        tail_df = pd.DataFrame(
            {
                "tail_number": ac["tail_number"],
                "flight_date": dates.date,
                "flight_hours": daily_hours,
                "flight_cycles": flight_cycles,
            }
        )
        all_rows.append(tail_df)
        cumulative_by_tail[ac["tail_number"]] = pd.Series(
            np.cumsum(daily_hours), index=dates
        )

    flight_hours_df = pd.concat(all_rows, ignore_index=True)
    return flight_hours_df, cumulative_by_tail


def _hours_to_date(cum_hours: pd.Series, target_hours: float) -> pd.Timestamp | None:
    """First date at which cumulative flight hours reach target_hours."""
    idx = np.searchsorted(cum_hours.values, target_hours, side="left")
    if idx >= len(cum_hours):
        return None
    return cum_hours.index[idx]


def simulate_maintenance_events(
    aircraft_df: pd.DataFrame,
    base_df: pd.DataFrame,
    cumulative_by_tail: dict[str, pd.Series],
    rng: np.random.Generator,
) -> pd.DataFrame:
    events = []
    event_id = 1
    home_base = {
        tail: base_df["base_code"].iloc[int(rng.integers(0, len(base_df)))]
        for tail in aircraft_df["tail_number"]
    }

    for tail, cum_hours in cumulative_by_tail.items():
        for comp in COMPONENTS:
            (code, _name, _ata, _category, _crit, unit_cost, _dc,
             beta, eta, mttr_mean, replace_hours, failure_modes) = comp

            clock_start = 0.0
            while True:
                ttf = float(rng.weibull(beta) * eta)
                if replace_hours is not None and ttf > replace_hours:
                    target = clock_start + replace_hours
                    event_type = "replacement"
                else:
                    target = clock_start + ttf
                    event_type = "failure"

                failed_at_date = _hours_to_date(cum_hours, target)
                if failed_at_date is None:
                    break  # ran past end of simulation window

                failed_at = pd.Timestamp(failed_at_date) + pd.Timedelta(
                    hours=float(rng.uniform(0, 23))
                )
                repair_hours = float(
                    rng.lognormal(mean=np.log(max(mttr_mean, 0.5)), sigma=0.5)
                )
                repair_hours = float(np.clip(repair_hours, 0.5, 200))
                repaired_at = failed_at + pd.Timedelta(hours=repair_hours)

                if event_type == "failure":
                    category = CATEGORY_OF[code]
                    weights = SEVERITY_WEIGHTS_BY_CATEGORY[category]
                    severity = rng.choice(
                        list(weights.keys()), p=list(weights.values())
                    )
                    parts_cost = unit_cost * rng.uniform(0.3, 1.0)
                else:  # replacement
                    severity = None
                    parts_cost = unit_cost * rng.uniform(0.9, 1.0)

                labor_cost = repair_hours * LABOR_RATE_PER_HOUR * rng.uniform(0.9, 1.1)
                base_code = (
                    home_base[tail]
                    if rng.random() < 0.9
                    else base_df["base_code"].iloc[int(rng.integers(0, len(base_df)))]
                )

                events.append(
                    {
                        "event_id": event_id,
                        "tail_number": tail,
                        "component_code": code,
                        "base_code": base_code,
                        "event_type": event_type,
                        "failure_mode": rng.choice(failure_modes) if event_type == "failure" else None,
                        "severity": severity,
                        "flight_hours_at_failure": round(target, 1),
                        "failed_at": failed_at,
                        "repaired_at": repaired_at,
                        "labor_cost": round(labor_cost, 2),
                        "parts_cost": round(parts_cost, 2),
                    }
                )
                event_id += 1
                clock_start = target  # renewal: clock resets to zero here

            # Scheduled inspections: fixed calendar cadence, independent of
            # the failure clock, short downtime, no parts cost.
            insp_dates = pd.date_range(
                cum_hours.index[0] + pd.Timedelta(days=180),
                cum_hours.index[-1],
                freq="180D",
            )
            for d in insp_dates:
                failed_at = d + pd.Timedelta(hours=float(rng.uniform(6, 10)))
                repair_hours = float(np.clip(rng.uniform(0.5, 2.0), 0.5, 4))
                events.append(
                    {
                        "event_id": event_id,
                        "tail_number": tail,
                        "component_code": code,
                        "base_code": home_base[tail],
                        "event_type": "scheduled",
                        "failure_mode": None,
                        "severity": None,
                        "flight_hours_at_failure": None,
                        "failed_at": failed_at,
                        "repaired_at": failed_at + pd.Timedelta(hours=repair_hours),
                        "labor_cost": round(repair_hours * LABOR_RATE_PER_HOUR, 2),
                        "parts_cost": round(unit_cost * rng.uniform(0.0, 0.05), 2),
                    }
                )
                event_id += 1

    events_df = pd.DataFrame(events).sort_values("failed_at").reset_index(drop=True)
    events_df["event_id"] = range(1, len(events_df) + 1)
    return events_df


def main() -> None:
    rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(exist_ok=True)
    SAMPLE_DIR.mkdir(exist_ok=True)

    aircraft_df, component_df, base_df = build_dimensions(rng)
    flight_hours_df, cumulative_by_tail = simulate_flight_hours(aircraft_df, rng)
    events_df = simulate_maintenance_events(aircraft_df, base_df, cumulative_by_tail, rng)

    aircraft_df.to_csv(DATA_DIR / "aircraft.csv", index=False)
    component_df.to_csv(DATA_DIR / "component.csv", index=False)
    base_df.to_csv(DATA_DIR / "base.csv", index=False)
    flight_hours_df.to_csv(DATA_DIR / "flight_hours.csv", index=False)
    events_df.to_csv(DATA_DIR / "maintenance_event.csv", index=False)

    # Small, deterministic samples committed to the repo so reviewers can
    # see the shape of the data without running the generator.
    aircraft_df.to_csv(SAMPLE_DIR / "aircraft_sample.csv", index=False)
    component_df.to_csv(SAMPLE_DIR / "component_sample.csv", index=False)
    base_df.to_csv(SAMPLE_DIR / "base_sample.csv", index=False)
    flight_hours_df.head(SAMPLE_N_FLIGHT_ROWS).to_csv(
        SAMPLE_DIR / "flight_hours_sample.csv", index=False
    )
    events_df.head(SAMPLE_N_EVENTS).to_csv(
        SAMPLE_DIR / "maintenance_event_sample.csv", index=False
    )

    print(f"aircraft:           {len(aircraft_df):>7,}")
    print(f"components:         {len(component_df):>7,}")
    print(f"bases:              {len(base_df):>7,}")
    print(f"flight_hours rows:  {len(flight_hours_df):>7,}")
    print(f"maintenance events: {len(events_df):>7,}")
    print(events_df["event_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
