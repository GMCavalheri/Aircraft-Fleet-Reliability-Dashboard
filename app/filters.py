"""Shared sidebar filters. Selections are stored in st.session_state so
they persist as the user navigates between the multipage app's pages
(Streamlit reruns the whole script on every page switch, so without
session_state the filters would reset)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st


def render_sidebar_filters(
    events: pd.DataFrame, flight_hours: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    st.sidebar.header("Filters")

    aircraft_types = sorted(events["aircraft_type"].unique())
    components = sorted(events["component_code"].unique())
    bases = sorted(events["base_code"].unique())
    min_date = events["failed_at"].min().date()
    max_date = events["failed_at"].max().date()

    sel_types = st.sidebar.multiselect(
        "Aircraft type", aircraft_types, default=st.session_state.get("f_types", aircraft_types)
    )
    sel_components = st.sidebar.multiselect(
        "Component", components, default=st.session_state.get("f_components", components)
    )
    sel_bases = st.sidebar.multiselect(
        "Maintenance base", bases, default=st.session_state.get("f_bases", bases)
    )
    sel_range = st.sidebar.slider(
        "Period",
        min_value=min_date,
        max_value=max_date,
        value=st.session_state.get("f_range", (min_date, max_date)),
    )

    st.session_state["f_types"] = sel_types
    st.session_state["f_components"] = sel_components
    st.session_state["f_bases"] = sel_bases
    st.session_state["f_range"] = sel_range

    start, end = sel_range
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)

    types = sel_types or aircraft_types
    comps = sel_components or components
    bs = sel_bases or bases

    filtered_events = events[
        events["aircraft_type"].isin(types)
        & events["component_code"].isin(comps)
        & events["base_code"].isin(bs)
        & events["failed_at"].between(start_ts, end_ts)
    ]
    filtered_hours = flight_hours[
        flight_hours["aircraft_type"].isin(types)
        & flight_hours["full_date"].between(start_ts, end_ts)
    ]
    return filtered_events, filtered_hours
