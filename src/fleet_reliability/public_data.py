"""Failure-category weights grounded in public aviation-safety statistics.

This module does not download raw NTSB/ASRS records at run time (their
public query tools return interactive HTML/CSV exports, not a stable
bulk API, and the exact download format changes over time). Instead it
encodes two *documented, citable* headline statistics from a published
NASA/NTSB study of accidents attributed to System/Component Failure or
Malfunction (SCFM), and uses them to weight how often each component
category in the synthetic fleet should fail relative to the others, and
how severe those failures should be.

Source: NASA/NTSB study of System- and Component-Failure/Malfunction
(SCFM) related accidents (NASA Technical Reports Server, document
20200002020, "Causal factors and adverse events of aviation accidents",
ntrs.nasa.gov). Of 370 NTSB accidents attributed to SCFM:
  - 48% involved the engine or fuel system
  - 31% involved landing gear or hydraulics

The remaining ~21% is not broken out at that resolution in the public
summary, so it is our own reasonable allocation across avionics/
electrical, flight controls, and structural/ECS/APU systems -- flagged
explicitly as an assumption, not a cited figure.

ASRS's own taxonomy (~180 subcategories under "Aircraft", ~130 under
"Event") confirms these are the right category buckets to use, even
though the fine-grained ASRS counts are not published as a simple
percentage table either.
"""

from __future__ import annotations

# Share of *failure events* attributed to each component category.
# Used by generate.py to keep the simulated fleet's failure mix
# realistic. The first two rows are cited; the rest are documented
# assumptions (see module docstring).
CATEGORY_FAILURE_SHARE: dict[str, float] = {
    "engine_fuel": 0.48,              # cited: NASA/NTSB SCFM study
    "landing_gear_hydraulics": 0.31,  # cited: NASA/NTSB SCFM study
    "avionics_electrical": 0.10,      # assumption
    "flight_controls": 0.06,          # assumption
    "structural_ecs_apu": 0.05,       # assumption
}

assert abs(sum(CATEGORY_FAILURE_SHARE.values()) - 1.0) < 1e-9

# Severity mix within each category: critical flight-safety systems
# (engine, landing gear/hydraulics) are given a higher share of
# major/critical outcomes than avionics or structural components,
# reflecting the SCFM study's overrepresentation of those two systems
# in *accidents* (not just any failure). This is our own assumption,
# not a cited per-category breakdown.
SEVERITY_WEIGHTS_BY_CATEGORY: dict[str, dict[str, float]] = {
    "engine_fuel":               {"minor": 0.55, "major": 0.35, "critical": 0.10},
    "landing_gear_hydraulics":   {"minor": 0.60, "major": 0.32, "critical": 0.08},
    "avionics_electrical":       {"minor": 0.75, "major": 0.22, "critical": 0.03},
    "flight_controls":           {"minor": 0.65, "major": 0.30, "critical": 0.05},
    "structural_ecs_apu":        {"minor": 0.80, "major": 0.18, "critical": 0.02},
}

for _cat, _weights in SEVERITY_WEIGHTS_BY_CATEGORY.items():
    assert abs(sum(_weights.values()) - 1.0) < 1e-9, _cat
