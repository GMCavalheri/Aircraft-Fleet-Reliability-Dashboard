"""Fleet reliability dashboard -- Overview page.

Run locally with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from data import load_events, load_flight_hours
from filters import render_sidebar_filters
from metrics import downtime_cost_by_category, kpis, monthly_failure_rate

st.set_page_config(page_title="Fleet reliability dashboard", page_icon="✈️", layout="wide")

st.title("Aircraft fleet reliability dashboard")
st.caption(
    "MTBF, MTTR, availability, and cost, computed live from the star-schema "
    "warehouse. Use the sidebar to filter by aircraft type, component, base, and period."
)

events = load_events()
flight_hours = load_flight_hours()
f_events, f_hours = render_sidebar_filters(events, flight_hours)

if f_events.empty or f_hours.empty:
    st.warning("No data matches the current filters.")
    st.stop()

m = kpis(f_events, f_hours)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Failures", f"{m['failure_count']:,}")
col2.metric("MTBF (flight hours)", f"{m['mtbf_hours']:,.0f}")
col3.metric("MTTR (hours)", f"{m['mttr_hours']:,.1f}")
col4.metric("Availability", f"{m['availability']:.3%}")
col5.metric(
    "Total estimated cost",
    f"${m['total_cost'] / 1e6:,.1f}M",
    help=f"${m['total_cost']:,.0f}",
)

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Failures per month by component category")
    monthly = monthly_failure_rate(f_events)
    if monthly.empty:
        st.info("No failures in the selected filters.")
    else:
        fig = px.bar(
            monthly,
            x="month",
            y="failure_count",
            color="component_category",
            labels={"month": "month", "failure_count": "failures", "component_category": "category"},
        )
        fig.update_layout(legend_title_text="category", margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Estimated cost by component category")
    cost = downtime_cost_by_category(f_events)
    if cost.empty:
        st.info("No failures in the selected filters.")
    else:
        fig = px.bar(
            cost.sort_values("total_estimated_cost"),
            x="total_estimated_cost",
            y="component_category",
            orientation="h",
            labels={"total_estimated_cost": "estimated cost ($)", "component_category": "category"},
        )
        fig.update_layout(margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Estimated cost = repair labor + parts actually spent, plus repair hours x "
    "the component's hourly downtime-cost assumption. See docs/metrics.md."
)
