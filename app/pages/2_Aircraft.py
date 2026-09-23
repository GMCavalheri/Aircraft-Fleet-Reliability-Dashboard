"""Aircraft comparison and per-tail event drill-down."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from data import load_events, load_flight_hours
from filters import render_sidebar_filters
from metrics import mtbf_by_aircraft

st.set_page_config(page_title="Aircraft - fleet reliability", page_icon="🛩️", layout="wide")
st.title("Aircraft comparison")

events = load_events()
flight_hours = load_flight_hours()
f_events, f_hours = render_sidebar_filters(events, flight_hours)

if f_hours.empty:
    st.warning("No data matches the current filters.")
    st.stop()

st.subheader("MTBF by aircraft")
by_ac = mtbf_by_aircraft(f_events, f_hours)
fig = px.bar(
    by_ac,
    x="mtbf_hours",
    y="tail_number",
    color="aircraft_type",
    orientation="h",
    labels={"mtbf_hours": "MTBF (flight hours)", "tail_number": "aircraft"},
    height=max(320, 24 * len(by_ac)),
)
fig.update_layout(margin=dict(t=10), legend_title_text="type")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Event history for one aircraft")
tail = st.selectbox("Aircraft", sorted(f_hours["tail_number"].unique()))
history = f_events[f_events["tail_number"] == tail].sort_values("failed_at", ascending=False)
st.dataframe(
    history[
        [
            "failed_at",
            "event_type",
            "component_code",
            "failure_mode",
            "severity",
            "repair_hours",
            "downtime_cost",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)
