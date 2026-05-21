"""R8-2C: serve the score explainer dicts.

Phase-2 item 1c. The frontend hits this once at boot, caches the result,
and shows the relevant block in a click-to-open modal when the `?`
info-mark in any score card is clicked.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.scoring.explainers import ALL_EXPLAINERS


router = APIRouter(tags=["scoring-meta"])


@router.get("/api/scoring/explainer")
def all_explainers():
    """Return Trend / Reversal / Overall explainers in one payload."""
    return {"available": True, "explainers": ALL_EXPLAINERS}


@router.get("/api/scoring/explainer/{kind}")
def one_explainer(kind: str):
    """Return a single explainer (kind ∈ {trend, reversal, overall})."""
    if kind not in ALL_EXPLAINERS:
        return {"available": False, "error": f"unknown explainer kind {kind}"}
    return {"available": True, "kind": kind, "explainer": ALL_EXPLAINERS[kind]}


@router.get("/api/scoring/calibrated")
def calibrated_status():
    """Calibrated (data-driven, sign-respecting) sleeve weights.

    Sourced from `backend/scoring/calibrated_weights.py`. The artifact is
    produced by `scripts/analyze_horizons.py` (multi-horizon Spearman rho)
    and consumed by `overall_score.resolve_weights("calibrated")`.

    Returns weights + per-sleeve audit (fmb_rho, t-stat, action) + the
    survivorship warning that *should* be displayed prominently in the UI.
    """
    import json
    from backend.config import DATA_DIR

    path = DATA_DIR / "scoring" / "calibrated_weights.json"
    if not path.exists():
        return {"available": False, "reason": "calibration artifact not generated yet"}
    try:
        payload = json.loads(path.read_text())
    except Exception as e:
        return {"available": False, "reason": f"file unreadable: {e}"}
    return {
        "available": True,
        "weights": payload.get("weights"),
        "contribution_signs": payload.get("contribution_signs"),
        "audit": payload.get("audit"),
        "by_horizon": payload.get("by_horizon"),
        "all_horizon_blend_weights": payload.get("all_horizon_blend_weights"),
        "horizon": payload.get("horizon"),
        "mode": payload.get("mode"),
        "t_threshold": payload.get("t_threshold"),
        "survivorship_warning": payload.get("survivorship_warning"),
        "panel_dimensions": payload.get("panel_dimensions"),
        "weight_rationale": payload.get("weight_rationale"),
        "generated_at": payload.get("generated_at"),
        # v2 schema (post-MIT peer-review): train-only vs full-sample
        # split, Newey-West HAC, Bonferroni gate, survivorship haircut,
        # within-sleeve atomic re-weighting experiment.
        "schema_version":            payload.get("schema_version"),
        "split":                     payload.get("split"),
        "use_nw":                    payload.get("use_nw"),
        "bonferroni_t":              payload.get("bonferroni_t"),
        "weights_full_sample":       payload.get("weights_full_sample"),
        "weights_train_only":        payload.get("weights_train_only"),
        "weights_train_only_bonferroni": payload.get("weights_train_only_bonferroni"),
        "weights_train_only_haircut":    payload.get("weights_train_only_haircut"),
        "weights_sensitivity_risk_minus_30pct":
            payload.get("weights_sensitivity_risk_minus_30pct"),
        "atomic_reweighted_trend":   payload.get("atomic_reweighted_trend"),
        "expected_live_haircut":     payload.get("expected_live_haircut"),
        # Sharpe-inversion verdict — the most important UI surface.
        "release_recommendation":    payload.get("release_recommendation"),
    }


@router.get("/api/scoring/tier_b")
def tier_b_status():
    """R8-4A: report whether Tier-B data-driven weights are accepted.

    UI Toggle (Theory ↔ Data-driven) should only render when accept=true.
    The training script (scripts/train_tier_b.py) runs walk-forward CV and
    accepts only if holdout Spearman ρ exceeds Tier-A by 0.02.
    """
    import json
    from backend.config import DATA_DIR

    path = DATA_DIR / "scoring" / "tier_b_weights.json"
    if not path.exists():
        return {"accept": False, "reason": "tier_b not yet trained", "available": False}
    try:
        payload = json.loads(path.read_text())
    except Exception as e:
        return {"accept": False, "reason": f"tier_b file unreadable: {e}", "available": False}
    return {
        "accept": bool(payload.get("accept")),
        "reason": payload.get("reason"),
        "weights": payload.get("weights"),
        "holdout_spearman_rho_5d_tier_b": payload.get("holdout_spearman_rho_5d_tier_b"),
        "holdout_spearman_rho_5d_tier_a": payload.get("holdout_spearman_rho_5d_tier_a"),
        "n_folds": payload.get("n_folds"),
        "available": True,
    }
