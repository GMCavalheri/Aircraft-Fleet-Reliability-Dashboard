"""Component reliability: Pareto and MTBF/MTTR/availability table."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from data import load_events, load_flight_hours
from filters import render_sidebar_filters
from metrics import availability_by_component, failure_pareto

st.set_page_config(page_title="Components - fleet reliability", page_icon="🔧", layout="wide")
st.title("Component reliability")

events = load_events()
flight_hours = load_flight_hours()
f_events, f_hours = render_sidebar_filters(events, flight_hours)

if f_events.empty:
    st.warning("No data matches the current filters.")
    st.stop()

st.subheader("Failure Pareto")
pareto = failure_pareto(f_events)
if pareto.empty:
    st.info("No failures in the selected filters.")
else:
    fig = go.Figure()
    fig.add_bar(x=pareto["component_code"], y=pareto["failure_count"], name="failures", yaxis="y1")
    fig.add_trace(
        go.Scatter(
            x=pareto["component_code"],
            y=pareto["cumulative_pct"],
            name="cumulative %",
            yaxis="y2",
            mode="lines+markers",
        )
    )
    fig.update_layout(
        yaxis=dict(title="failure count"),
        yaxis2=dict(title="cumulative %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=10),
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("MTBF, MTTR and availability by component")
avail = availability_by_component(f_events, f_hours)
if avail.empty:
    st.info("No failures in the selected filters.")
else:
    display = avail.copy()
    display["mtbf_hours"] = display["mtbf_hours"].round(0)
    display["mttr_hours"] = display["mttr_hours"].round(1)
    display["availability"] = (display["availability"] * 100).round(3)
    display = display.rename(
        columns={
            "component_code": "component",
            "component_name": "name",
            "component_category": "category",
            "failure_count": "failures",
            "mtbf_hours": "MTBF (fh)",
            "mttr_hours": "MTTR (h)",
            "availability": "availability (%)",
        }
    )
    st.dataframe(
        display[["component", "name", "category", "failures", "MTBF (fh)", "MTTR (h)", "availability (%)"]],
        use_container_width=True,
        hide_index=True,
    )
