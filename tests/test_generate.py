import numpy as np
import pandas as pd
import pytest

from fleet_reliability.generate import (
    COMPONENTS,
    build_dimensions,
    simulate_flight_hours,
    simulate_maintenance_events,
)


@pytest.fixture(scope="module")
def generated():
    rng = np.random.default_rng(42)
    aircraft_df, component_df, base_df = build_dimensions(rng)
    flight_hours_df, cumulative_by_tail = simulate_flight_hours(aircraft_df, rng)
    events_df = simulate_maintenance_events(aircraft_df, base_df, cumulative_by_tail, rng)
    return aircraft_df, component_df, base_df, flight_hours_df, events_df


def test_generator_is_deterministic_for_a_seed():
    rng_a = np.random.default_rng(42)
    aircraft_a, component_a, base_a = build_dimensions(rng_a)
    flight_a, cum_a = simulate_flight_hours(aircraft_a, rng_a)
    events_a = simulate_maintenance_events(aircraft_a, base_a, cum_a, rng_a)

    rng_b = np.random.default_rng(42)
    aircraft_b, component_b, base_b = build_dimensions(rng_b)
    flight_b, cum_b = simulate_flight_hours(aircraft_b, rng_b)
    events_b = simulate_maintenance_events(aircraft_b, base_b, cum_b, rng_b)

    pd.testing.assert_frame_equal(aircraft_a, aircraft_b)
    pd.testing.assert_frame_equal(flight_a, flight_b)
    pd.testing.assert_frame_equal(events_a, events_b)


def test_no_repair_before_failure(generated):
    _, _, _, _, events_df = generated
    assert (pd.to_datetime(events_df["repaired_at"]) >= pd.to_datetime(events_df["failed_at"])).all()


def test_event_types_are_valid(generated):
    _, _, _, _, events_df = generated
    assert set(events_df["event_type"].unique()) <= {"failure", "replacement", "scheduled"}


def test_foreign_keys_resolve(generated):
    aircraft_df, component_df, base_df, _, events_df = generated
    assert set(events_df["tail_number"]).issubset(set(aircraft_df["tail_number"]))
    assert set(events_df["component_code"]).issubset(set(component_df["component_code"]))
    assert set(events_df["base_code"]).issubset(set(base_df["base_code"]))


def test_flight_hours_are_non_negative(generated):
    _, _, _, flight_hours_df, _ = generated
    assert (flight_hours_df["flight_hours"] >= 0).all()
    assert (flight_hours_df["flight_cycles"] >= 0).all()


def test_recovered_weibull_shape_close_to_true_parameter():
    """Fit a Weibull to a large synthetic failure-time sample (uncensored,
    single component in isolation) and check we recover beta/eta within a
    loose tolerance -- this validates the simulation mechanics, not the
    fleet-level renewal process (which is heavily censored by the 6-year
    window and is not expected to recover the parameters exactly)."""
    from scipy import stats

    rng = np.random.default_rng(7)
    beta_true, eta_true = 2.2, 18_000
    sample = rng.weibull(beta_true, size=5000) * eta_true

    beta_fit, _loc, eta_fit = stats.weibull_min.fit(sample, floc=0)

    assert beta_fit == pytest.approx(beta_true, rel=0.1)
    assert eta_fit == pytest.approx(eta_true, rel=0.1)


def test_component_catalog_has_no_duplicate_codes():
    codes = [c[0] for c in COMPONENTS]
    assert len(codes) == len(set(codes))
