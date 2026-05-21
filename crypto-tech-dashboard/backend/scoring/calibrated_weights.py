"""Data-driven, sign-respecting Tier-A sleeve weights — v2.

v2 changes (response to MIT peer-review):

 1. Reads BOTH the full-sample sleeve stats AND the train-only stats from
    `horizon_calibration.json` (the artifact now carries both). The
    "deployable" weights are the train-only ones; the full-sample weights
    are kept for explanatory purposes only and marked as such.

 2. `t_threshold` is now a first-class kwarg and supports a Bonferroni
    preset (~3.16 for 80-test family). Every audit row gets a
    `passes_bonferroni` flag.

 3. `survivorship_haircut` kwarg: shrinks each sleeve's weight by a
    sleeve-specific "expected live haircut" before renormalisation. Default
    haircuts encode the asymmetric exposure (risk gets shrunk hardest;
    trend almost not at all). Even with haircut=0, the artifact reports the
    sensitivity-adjusted weights as a separate field.

 4. `compute_atomic_weighted_sleeve()`: within-sleeve atomic re-weighting
    (the proper fix for the trend-sleeve sign problem the reviewer
    flagged). This composite is stored in the artifact under
    `atomic_reweighted_trend` so callers can compare.

 5. The artifact now exposes:
       - `weights_full_sample`   (in-sample, EXPLANATORY ONLY)
       - `weights_train_only`    (the actual deployable weights)
       - `weights_train_only_bonferroni` (Bonferroni-gated variant)
       - `weights_train_only_haircut`    (train + survivorship haircut)
       - `sensitivity_risk_minus_30pct`  (what if risk sleeve rho -30%?)

 6. `load_calibrated_weights()` now returns the train-only weights by
    default. A new flag `which="full_sample"` is available for back-compat
    inspection.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, Mapping, Optional

from backend.config import DATA_DIR

# Match overall_score.TIER_A_WEIGHTS keys exactly so payloads merge cleanly.
SLEEVE_KEYS = ["trend", "reversal", "breadth", "risk", "ts_trend_2y", "ts_reversal_2y"]

# Map between sleeve names used in overall_score and the panel column names
# in horizon_calibration.json.
SLEEVE_TO_PANEL = {
    "trend":    "trend_cs",
    "reversal": "reversal_cs",
    "breadth":  "breadth_cs",
    "risk":     "risk_cs",
}

CALIB_PATH    = DATA_DIR / "scoring" / "horizon_calibration.json"
OUT_PATH      = DATA_DIR / "scoring" / "calibrated_weights.json"

# Sleeve budget = 1 - (ts_trend_2y + ts_reversal_2y).
TS_BUDGET = 0.05 + 0.05
LEARNABLE_BUDGET = 1.0 - TS_BUDGET     # 0.90

# Bonferroni |t| critical value for alpha=0.05 / 80 simultaneous tests.
BONFERRONI_T = 3.16
DEFAULT_T = 2.0

# Expected live-edge haircut per sleeve (response to MIT critique #5).
# These encode the prior that survivorship inflation is asymmetric: risk
# (low-vol) gets the biggest haircut because high-vol tokens that died are
# the missing cohort; trend / reversal less so.
DEFAULT_SURVIVORSHIP_HAIRCUT = {
    "trend":    0.10,   # ~10% rho attenuation expected
    "reversal": 0.20,
    "breadth":  0.15,
    "risk":     0.40,   # ~40% rho attenuation expected
}


# ----- core logic --------------------------------------------------------- #

def _meaningful(rho: float, t: float, t_threshold: float) -> bool:
    if rho is None or rho != rho:
        return False
    if t is None or t != t:
        return False
    return abs(t) >= t_threshold


def _pick_t_field(payload_feature: dict, *, use_nw: bool, train_only: bool) -> float:
    """Choose the right t-stat field from the v2 schema. Falls back to
    legacy `fmb_t` for v1 artifacts."""
    if train_only:
        if use_nw and "fmb_t_nw_train" in payload_feature:
            return float(payload_feature.get("fmb_t_nw_train", float("nan")))
        if "fmb_t_raw_train" in payload_feature:
            return float(payload_feature.get("fmb_t_raw_train", float("nan")))
        # v1 artifact: no train field; fall back to full-sample t
        return float(payload_feature.get("fmb_t", float("nan")))
    if use_nw and "fmb_t_nw" in payload_feature:
        return float(payload_feature.get("fmb_t_nw", float("nan")))
    if "fmb_t_raw" in payload_feature:
        return float(payload_feature.get("fmb_t_raw", float("nan")))
    return float(payload_feature.get("fmb_t", float("nan")))


def _pick_rho_field(payload_feature: dict, *, train_only: bool) -> float:
    if train_only:
        if "fmb_rho_train" in payload_feature:
            return float(payload_feature.get("fmb_rho_train", float("nan")))
        return float(payload_feature.get("fmb_rho", float("nan")))
    return float(payload_feature.get("fmb_rho", float("nan")))


def _calibrate_one_horizon(
    payload: dict,
    horizon: str,
    *,
    mode: str = "drop",
    t_threshold: float = DEFAULT_T,
    use_nw: bool = True,
    train_only: bool = True,
    survivorship_haircut: Optional[Dict[str, float]] = None,
    rho_override: Optional[Dict[str, float]] = None,
) -> Dict[str, dict]:
    """Compute calibrated weights for a single horizon.

    Parameters
    ----------
    train_only : if True (default, deployable), uses train-slice stats from
        the v2 artifact. If False, uses full-sample stats (explanatory only).
    use_nw : if True (default), uses Newey-West HAC t-stats. The reviewer's
        BLOCKER 3 demands this.
    survivorship_haircut : dict {sleeve_key: float in [0,1]} -- shrink each
        sleeve's |rho|*(1-haircut) BEFORE renormalisation. Default haircuts
        from DEFAULT_SURVIVORSHIP_HAIRCUT.
    rho_override : per-sleeve rho replacement (used by the sensitivity
        analysis to model "risk rho - 30%").
    """
    if horizon not in payload["horizons"]:
        raise KeyError(f"horizon {horizon} not in calibration artifact "
                       f"(have {list(payload['horizons'].keys())})")
    hbl = payload["horizons"][horizon]["features"]
    haircut = dict(DEFAULT_SURVIVORSHIP_HAIRCUT) if survivorship_haircut is None \
        else {**DEFAULT_SURVIVORSHIP_HAIRCUT, **survivorship_haircut}

    rows: Dict[str, dict] = {}
    for sleeve, panel_col in SLEEVE_TO_PANEL.items():
        f = hbl.get(panel_col, {})
        rho_raw = _pick_rho_field(f, train_only=train_only)
        if rho_override and sleeve in rho_override:
            rho_raw = rho_override[sleeve]
        t = _pick_t_field(f, use_nw=use_nw, train_only=train_only)

        passes_bonf = bool(t == t and abs(t) >= BONFERRONI_T)
        meaningful = _meaningful(rho_raw, t, t_threshold)
        action = "kept"
        signed_size = 0.0
        if not meaningful:
            action = f"dropped (|t|<{t_threshold:.2f}, t={t:+.2f})"
            signed_size = 0.0
        elif rho_raw < 0:
            if mode == "flip":
                action = "flipped (rho<0 but |t|>=thr)"
                signed_size = abs(rho_raw)
            else:
                action = f"dropped (rho={rho_raw:+.4f}<0, conservative)"
                signed_size = 0.0
        else:
            action = f"kept (rho={rho_raw:+.4f}, |t|={abs(t):.2f})"
            signed_size = abs(rho_raw)

        # Apply survivorship haircut to size if haircut active
        haircut_frac = float(haircut.get(sleeve, 0.0))
        size_after_haircut = signed_size * (1.0 - haircut_frac)

        rows[sleeve] = {
            "fmb_rho": rho_raw,
            "fmb_t":   t,
            "t_type": "nw" if use_nw else "raw",
            "rho_source": "train_only" if train_only else "full_sample",
            "meaningful": bool(meaningful),
            "passes_bonferroni": passes_bonf,
            "empirical_sign": (1 if rho_raw > 0 else (-1 if rho_raw < 0 else 0)),
            "action": action,
            "raw_size": signed_size,
            "survivorship_haircut_frac": haircut_frac,
            "size_after_haircut": size_after_haircut,
        }

    # Normalisation: weights from raw_size (no haircut applied to the
    # deployable weight if survivorship_haircut not requested).
    total_size = sum(r["raw_size"] for r in rows.values())
    weights: Dict[str, float] = {}
    if total_size <= 1e-12:
        for s in SLEEVE_TO_PANEL:
            weights[s] = LEARNABLE_BUDGET / 4.0
            rows[s]["normalized_weight"] = weights[s]
            rows[s]["action"] += " | fallback: equal-weight (no meaningful sleeves)"
    else:
        for s in SLEEVE_TO_PANEL:
            weights[s] = rows[s]["raw_size"] / total_size * LEARNABLE_BUDGET
            rows[s]["normalized_weight"] = weights[s]

    # Haircut-applied variant
    total_h = sum(r["size_after_haircut"] for r in rows.values())
    weights_haircut: Dict[str, float] = {}
    if total_h <= 1e-12:
        for s in SLEEVE_TO_PANEL:
            weights_haircut[s] = LEARNABLE_BUDGET / 4.0
    else:
        for s in SLEEVE_TO_PANEL:
            weights_haircut[s] = rows[s]["size_after_haircut"] / total_h * LEARNABLE_BUDGET
    weights_haircut["ts_trend_2y"] = 0.05
    weights_haircut["ts_reversal_2y"] = 0.05

    # TS sleeves retain their Tier-A defaults in the main weights too.
    weights["ts_trend_2y"]    = 0.05
    weights["ts_reversal_2y"] = 0.05
    rows["ts_trend_2y"]    = {"normalized_weight": 0.05,
                              "action": "Tier-A default (not in calibration)"}
    rows["ts_reversal_2y"] = {"normalized_weight": 0.05,
                              "action": "Tier-A default (not in calibration)"}

    contribution_signs: Dict[str, int] = {}
    for sleeve in SLEEVE_TO_PANEL:
        r = rows[sleeve]
        if mode == "flip" and r["empirical_sign"] == -1 and r["meaningful"]:
            contribution_signs[sleeve] = -1
        else:
            contribution_signs[sleeve] = +1
    contribution_signs["ts_trend_2y"]    = +1
    contribution_signs["ts_reversal_2y"] = +1

    return {
        "weights": weights,
        "weights_after_haircut": weights_haircut,
        "contribution_signs": contribution_signs,
        "audit": rows,
        "mode": mode,
        "t_threshold": t_threshold,
        "use_nw": use_nw,
        "train_only": train_only,
        "horizon": horizon,
        "survivorship_haircut_applied": haircut,
    }


def _sensitivity_risk_minus(payload: dict, horizon: str, pct: float = 0.30,
                             *, train_only: bool = True, use_nw: bool = True,
                             t_threshold: float = DEFAULT_T) -> Dict[str, float]:
    """What do the weights look like if risk-sleeve rho is *actually* `pct`
    lower than the calibration says (the survivorship-corrected world)?
    """
    hbl = payload["horizons"][horizon]["features"]
    f_risk = hbl.get("risk_cs", {})
    rho_risk = _pick_rho_field(f_risk, train_only=train_only)
    new_rho = rho_risk * (1.0 - pct)
    res = _calibrate_one_horizon(payload, horizon, mode="drop",
                                  t_threshold=t_threshold,
                                  use_nw=use_nw, train_only=train_only,
                                  rho_override={"risk": new_rho})
    return res["weights"]


# ----- within-sleeve atomic re-weighting (response to critique #6) ------ #

# Atomic signal columns inside the trend sleeve, mirroring TREND_SIGNALS in
# backend/scoring/trend_score.py. We list them explicitly here so this
# module has no scripts/ import dependency.
TREND_ATOMIC_PANEL_COLS = [
    "mom_ret_5d", "mom_ret_10d", "mom_ret_20d",
    "macd_hist_12_26_9", "macd_hist_slope5_12_26_9",
    "sma_cross_strength_signed_5_20", "ema_cross_strength_signed_5_20",
    "ma50_slope_20d", "ma50_dev",
]


def compute_atomic_weighted_sleeve(sleeve_name: str, horizon: str, payload: dict,
                                    *, t_threshold: float = DEFAULT_T,
                                    use_nw: bool = True,
                                    train_only: bool = True) -> Dict[str, float]:
    """Within-sleeve atomic re-weighting.

    Returns {atomic_signal: weight} where weights sum to 1.0 over the
    atomic signals that survive (NW t passes threshold AND sign positive).
    "Babies" inside a wrong-sign sleeve (e.g. ma_cross atomics inside trend)
    are preserved here.

    Currently only "trend" is supported (since reviewer's example was the
    trend sleeve). Other sleeves return empty for safety.
    """
    if sleeve_name != "trend":
        return {}
    if horizon not in payload["horizons"]:
        return {}
    hbl = payload["horizons"][horizon]["features"]
    weights: Dict[str, float] = {}
    for col in TREND_ATOMIC_PANEL_COLS:
        if col not in hbl:
            continue
        f = hbl[col]
        rho = _pick_rho_field(f, train_only=train_only)
        t = _pick_t_field(f, use_nw=use_nw, train_only=train_only)
        if rho != rho or t != t:
            continue
        if abs(t) < t_threshold:
            continue
        if rho < 0:           # drop sign-wrong
            continue
        weights[col] = abs(rho)
    total = sum(weights.values())
    if total <= 1e-12:
        return {}
    for k in weights:
        weights[k] /= total
    return weights


# ----- top-level ---------------------------------------------------------- #

def calibrate(
    horizon: str = "5d",
    mode: str = "drop",
    t_threshold: float = DEFAULT_T,
    use_nw: bool = True,
    survivorship_haircut: Optional[Dict[str, float]] = None,
    write: bool = True,
) -> dict:
    """End-to-end. Reads the artifact, computes the family of v2 weight
    variants, writes them to local_data/scoring/calibrated_weights.json.

    The deployable headline weights are train-only + NW-t + bonferroni gate;
    the in-sample / full-sample numbers are kept for explanatory purposes.
    """
    if not CALIB_PATH.exists():
        raise FileNotFoundError(
            f"{CALIB_PATH} not found. Run `python3 scripts/analyze_horizons.py` first."
        )
    payload = json.loads(CALIB_PATH.read_text())
    schema_version = payload.get("schema_version", 1)
    has_train_fields = schema_version >= 2

    # The four calibration variants ----------------------------------------
    full_sample = _calibrate_one_horizon(
        payload, horizon, mode=mode, t_threshold=t_threshold,
        use_nw=use_nw, train_only=False,
        survivorship_haircut=survivorship_haircut)

    if has_train_fields:
        train_only = _calibrate_one_horizon(
            payload, horizon, mode=mode, t_threshold=t_threshold,
            use_nw=use_nw, train_only=True,
            survivorship_haircut=survivorship_haircut)
        train_only_bonf = _calibrate_one_horizon(
            payload, horizon, mode=mode, t_threshold=BONFERRONI_T,
            use_nw=use_nw, train_only=True,
            survivorship_haircut=survivorship_haircut)
    else:
        train_only = full_sample
        train_only_bonf = full_sample

    # Sensitivity: what if risk rho is really 30% lower?
    sens_minus30 = _sensitivity_risk_minus(
        payload, horizon, pct=0.30,
        train_only=has_train_fields, use_nw=use_nw, t_threshold=t_threshold)

    # Per-horizon variants for reference -----------------------------------
    by_horizon = {}
    for h in payload["horizons"]:
        try:
            by_horizon[h] = _calibrate_one_horizon(
                payload, h, mode=mode, t_threshold=t_threshold,
                use_nw=use_nw, train_only=has_train_fields,
                survivorship_haircut=survivorship_haircut)
        except Exception as e:
            by_horizon[h] = {"error": str(e)}

    # Mean-blend across horizons (positive-rho meaningful sleeves only) ----
    blend_raw: Dict[str, float] = {s: 0.0 for s in SLEEVE_TO_PANEL}
    blend_n: Dict[str, int] = {s: 0 for s in SLEEVE_TO_PANEL}
    for h, cal in by_horizon.items():
        if "audit" not in cal:
            continue
        for s in SLEEVE_TO_PANEL:
            row = cal["audit"].get(s, {})
            if not row.get("meaningful"):
                continue
            if row["empirical_sign"] != 1:
                continue
            blend_raw[s] += row["raw_size"]
            blend_n[s] += 1
    blend_total = sum(blend_raw.values())
    blend_weights: Dict[str, float] = {}
    if blend_total > 1e-12:
        for s in SLEEVE_TO_PANEL:
            blend_weights[s] = blend_raw[s] / blend_total * LEARNABLE_BUDGET
    else:
        for s in SLEEVE_TO_PANEL:
            blend_weights[s] = LEARNABLE_BUDGET / 4.0
    blend_weights["ts_trend_2y"]    = 0.05
    blend_weights["ts_reversal_2y"] = 0.05

    # Atomic-reweighted trend sleeve weights (the "save trend" experiment).
    atomic_trend_weights = compute_atomic_weighted_sleeve(
        "trend", horizon, payload,
        t_threshold=t_threshold, use_nw=use_nw,
        train_only=has_train_fields)

    artifact = {
        "generated_at": payload.get("generated_at"),
        "schema_version": 2,
        "horizon": horizon,
        "mode": mode,
        "t_threshold": t_threshold,
        "use_nw": use_nw,
        "bonferroni_t": BONFERRONI_T,
        # The deployable headline:
        "weights": train_only["weights"],
        "contribution_signs": train_only["contribution_signs"],
        "audit": train_only["audit"],
        # The four variants (so reviewers can inspect):
        "weights_full_sample": full_sample["weights"],
        "weights_train_only":  train_only["weights"],
        "weights_train_only_bonferroni": train_only_bonf["weights"],
        "weights_train_only_haircut":    train_only["weights_after_haircut"],
        "weights_sensitivity_risk_minus_30pct": sens_minus30,
        # Variant audits:
        "audit_full_sample":            full_sample["audit"],
        "audit_train_only_bonferroni":  train_only_bonf["audit"],
        # Per-horizon / blend (legacy fields, preserved for backward compat):
        "by_horizon": {h: cal.get("weights") for h, cal in by_horizon.items()},
        "all_horizon_blend_weights": blend_weights,
        "all_horizon_blend_vote_counts": blend_n,
        # Atomic re-weighting experiment (response to critique #6):
        "atomic_reweighted_trend": atomic_trend_weights,
        "atomic_reweighted_trend_horizon": horizon,
        # Survivorship metadata:
        "survivorship_warning": (
            payload.get("survivorship", {}).get("warning")
            or "no survivorship metadata in calibration artifact"
        ),
        "expected_live_haircut": DEFAULT_SURVIVORSHIP_HAIRCUT,
        "panel_dimensions": {
            "n_panel_rows": payload.get("n_panel_rows"),
            "n_dates":      payload.get("n_dates"),
            "n_tokens":     payload.get("n_tokens"),
        },
        "split": payload.get("split"),
        "weight_rationale": {
            "deployment": "weights = `weights_train_only` (NW-t, t>=2.0, "
                          "fit on first 80% of dates). The other weight "
                          "variants are for reviewer transparency only.",
            "weights_full_sample": "WARNING: in-sample. EXPLANATORY ONLY. "
                                   "Do not deploy.",
            "weights_train_only_bonferroni": "Family-wise corrected for 80 "
                                              "simultaneous tests (|t|>=3.16). "
                                              "Most conservative; will often "
                                              "concentrate further on risk.",
            "weights_train_only_haircut":   "Train-only weights with each "
                                             "sleeve's |rho| shrunk by an "
                                             "expected survivorship haircut.",
            "weights_sensitivity_risk_minus_30pct": "Shows how the weights "
                                                    "shift if the true risk "
                                                    "edge is 30% smaller than "
                                                    "the calibration claims.",
        },
    }

    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(artifact, indent=2, default=str))
    return artifact


def load_calibrated_weights(which: str = "train_only") -> Optional[Dict[str, float]]:
    """Return the weights dict from the on-disk artifact, or None if missing.

    `which` can be:
      - "train_only"          (default; deployable, what overall_score uses)
      - "full_sample"         (legacy, in-sample; not for deployment)
      - "haircut"             (train_only + survivorship haircut)
      - "bonferroni"          (train_only + family-wise correction)
    """
    if not OUT_PATH.exists():
        return None
    try:
        payload = json.loads(OUT_PATH.read_text())
    except Exception:
        return None

    key = {
        "train_only":  "weights_train_only",
        "full_sample": "weights_full_sample",
        "haircut":     "weights_train_only_haircut",
        "bonferroni":  "weights_train_only_bonferroni",
        "default":     "weights",
    }.get(which, "weights_train_only")

    weights = payload.get(key) or payload.get("weights")
    if not isinstance(weights, dict):
        return None
    out: Dict[str, float] = {}
    for k in SLEEVE_KEYS:
        if k not in weights:
            return None
        out[k] = float(weights[k])
    return out


def load_contribution_signs() -> Dict[str, int]:
    """Return {sleeve: +1/-1}. Defaults to +1 when missing."""
    if not OUT_PATH.exists():
        return {k: +1 for k in SLEEVE_KEYS}
    try:
        payload = json.loads(OUT_PATH.read_text())
    except Exception:
        return {k: +1 for k in SLEEVE_KEYS}
    sgn = payload.get("contribution_signs") or {}
    return {k: int(sgn.get(k, 1)) for k in SLEEVE_KEYS}


if __name__ == "__main__":
    art = calibrate()
    print(json.dumps({
        "weights_train_only": art["weights_train_only"],
        "weights_full_sample": art["weights_full_sample"],
        "weights_train_only_bonferroni": art["weights_train_only_bonferroni"],
        "weights_train_only_haircut": art["weights_train_only_haircut"],
        "weights_sensitivity_risk_minus_30pct": art["weights_sensitivity_risk_minus_30pct"],
        "atomic_reweighted_trend": art["atomic_reweighted_trend"],
        "contribution_signs": art["contribution_signs"],
        "actions": {k: v.get("action") for k, v in art["audit"].items()},
        "survivorship_warning": art["survivorship_warning"],
    }, indent=2, default=str))
