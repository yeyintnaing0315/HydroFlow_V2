from typing import Literal

RiskLevel = Literal["low", "moderate", "high", "severe"]
FloodBand = Literal["low", "moderate", "high", "very_high"]


def academic_risk_score(
    precipitation_mm: float, discharge_m3_s: float, predicted_value: float = 0
) -> tuple[float, RiskLevel]:
    """Deterministic academic heuristic, not an operational warning."""
    score = min(
        100.0,
        max(0.0, precipitation_mm) * 1.25
        + max(0.0, discharge_m3_s) * 0.04
        + max(0.0, predicted_value) * 10,
    )
    if score < 25:
        level: RiskLevel = "low"
    elif score < 50:
        level = "moderate"
    elif score < 75:
        level = "high"
    else:
        level = "severe"
    return round(score, 2), level


def horizon_probability(probabilities: list[float | None]) -> float | None:
    """Chance of at least one flood day. Missing days are left out, not treated as dry."""
    known = [min(1.0, max(0.0, float(value))) for value in probabilities if value is not None]
    if not known:
        return None
    remain = 1.0
    for value in known:
        remain *= 1.0 - value
    return 1.0 - remain


def flood_probability_band(probability: float) -> FloodBand:
    """Displayed flood bands: low <25%, moderate <50%, high <75%, very high from 75%."""
    if probability < 0.25:
        return "low"
    if probability < 0.50:
        return "moderate"
    if probability < 0.75:
        return "high"
    return "very_high"


def band_to_risk_level(band: str | None) -> str:
    """Map the stored band onto the existing low/moderate/high/severe colors."""
    if band == "very_high":
        return "severe"
    if band in {"low", "moderate", "high", "severe"}:
        return band
    return "unknown"
