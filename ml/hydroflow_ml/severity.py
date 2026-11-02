from __future__ import annotations

import pandas as pd


def academic_impact_severity(
    households: pd.Series, affected_people: pd.Series
) -> pd.Series:
    """Rule-based retrospective impact category; not an ML prediction."""
    households = pd.to_numeric(households, errors="coerce").fillna(0).clip(lower=0)
    people = pd.to_numeric(affected_people, errors="coerce").fillna(0).clip(lower=0)
    score = households + people / 5.0
    severity = pd.Series("none", index=score.index, dtype="string")
    severity.loc[score > 0] = "low"
    severity.loc[score >= 100] = "moderate"
    severity.loc[score >= 500] = "high"
    severity.loc[score >= 2000] = "severe"
    return severity
