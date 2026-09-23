"""Weibull time-to-failure fit for one component.

Uses the full fleet history (not the sidebar filters) because a Weibull
MLE fit needs as many observations as possible -- narrowing the sample
first, then fitting, would defeat the point. Since this project's data
is synthetic, we know the *true* generating (beta, eta) for each
component (see src/fleet_reliability/generate.py) and show it next to
the fitted value as a sanity check on the whole pipeline.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

from data import load_time_between_failures
from fleet_reliability.generate import COMPONENTS

st.set_page_config(page_title="Weibull - fleet reliability", page_icon="📉", layout="wide")
st.title("Weibull time-to-failure fit")
st.caption(
    "Fits scipy.stats.weibull_min to the observed time-between-failures for one "
    "component, using the full fleet history (sidebar filters do not apply on this page)."
)

TRUE_PARAMS = {c[0]: {"beta": c[7], "eta": c[8]} for c in COMPONENTS}
NAMES = {c[0]: c[1] for c in COMPONENTS}

component = st.selectbox("Component", sorted(TRUE_PARAMS), format_func=lambda c: f"{c} - {NAMES[c]}")

tbf = load_time_between_failures()
sample_values = tbf.loc[
    (tbf["component_code"] == component) & (tbf["hours_since_last_event"] > 1),
    "hours_since_last_event",
].to_numpy()

st.write(f"Sample size: {len(sample_values):,} time-to-failure observations")

if len(sample_values) < 5:
    st.warning("Not enough failures for this component to fit a Weibull distribution reliably.")
    st.stop()

beta_fit, _loc, eta_fit = stats.weibull_min.fit(sample_values, floc=0)
true = TRUE_PARAMS[component]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Fitted beta (shape)", f"{beta_fit:.2f}")
col2.metric("True beta (generator)", f"{true['beta']:.2f}")
col3.metric("Fitted eta (scale, fh)", f"{eta_fit:,.0f}")
col4.metric("True eta (generator, fh)", f"{true['eta']:,.0f}")

t = np.linspace(1, max(sample_values.max(), true["eta"]) * 1.3, 300)
hazard_fit = (beta_fit / eta_fit) * (t / eta_fit) ** (beta_fit - 1) * 1000
hazard_true = (true["beta"] / true["eta"]) * (t / true["eta"]) ** (true["beta"] - 1) * 1000

fig = go.Figure()
fig.add_trace(go.Histogram(x=sample_values, histnorm="probability density", name="observed", opacity=0.5))
pdf_fit = stats.weibull_min.pdf(t, beta_fit, loc=0, scale=eta_fit)
fig.add_trace(go.Scatter(x=t, y=pdf_fit, name="fitted Weibull pdf", mode="lines"))
fig.update_layout(
    title="Observed time-to-failure vs. fitted Weibull",
    xaxis_title="flight hours since last event",
    yaxis_title="density",
    margin=dict(t=40),
)
st.plotly_chart(fig, use_container_width=True)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=t, y=hazard_fit, name="fitted hazard", mode="lines"))
fig2.add_trace(go.Scatter(x=t, y=hazard_true, name="true hazard", mode="lines", line=dict(dash="dash")))
fig2.update_layout(
    title="Hazard rate: fitted vs. true generating distribution",
    xaxis_title="flight hours",
    yaxis_title="failures per 1,000 flight hours",
    margin=dict(t=40),
)
st.plotly_chart(fig2, use_container_width=True)

if beta_fit > 1.05:
    regime = "wear-out (hazard increases with age) -- a preventive replacement program helps."
elif beta_fit < 0.95:
    regime = "early-life/infant mortality (hazard decreases with age) -- points at a manufacturing or burn-in issue."
else:
    regime = "roughly constant hazard (random failures) -- age-based maintenance would not help much."
st.info(f"Shape parameter beta = {beta_fit:.2f} indicates: {regime}")
