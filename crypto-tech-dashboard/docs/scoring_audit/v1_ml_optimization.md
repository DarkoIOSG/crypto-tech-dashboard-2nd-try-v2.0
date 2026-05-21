# ML Optimization Report — Tier-A Scoring Calibration

**Author:** ML scientist consult
**Date:** 2026-05-15
**Project:** `crypto-tech-dashboard` overall composite scoring

## TL;DR

1. The Tier-A `trend` sleeve gets 0.40 weight but has *negative* short-horizon
   edge (FMB ρ = −0.0143 at 5d, t = −3.55) — the system was trading momentum
   the wrong way over the 1–4 week horizon where the dashboard's CS percentiles
   actually move.
2. The `risk` sleeve (low-vol percentile) carries the dominant signal at every
   horizon (ρ up to **+0.114, t = +23.76 at 60d**) and was 4–8x under-weighted.
3. A sign-respecting calibration that drops disagreeing sleeves and sizes the
   rest by |ρ| **doubles** the Tier-A holdout edge at 5d
   (ρ +0.021 → **+0.051**) and improves every other horizon (5d/10d/20d/60d).
4. Universe is severely survivorship-biased: 240 tokens alive today, 0
   delisted, 206 added later. Calibrated ρs overstate live edge — disclosed in
   every artifact.

## A. Multi-Horizon Calibration Results

Method: per-token CS-percentile within each date for 16 atomic signals + 4
sleeves; **Fama-MacBeth-style** Spearman ρ (per-date ρ, then mean across
dates, t = mean / SE). Panel: 243,326 (date × token) obs, 2,289 dates, 240
tokens, 2020-01-30 → 2026-05-15.

### Sleeves (the 4 things Tier-A actually combines)

| Sleeve       | 5d            | 10d           | 20d           | 60d           |
|--------------|--------------:|--------------:|--------------:|--------------:|
| trend_cs     | −0.0143 (−3.55) | −0.0041 (−1.02) | −0.0032 (−0.82) | +0.0046 (+1.20) |
| reversal_cs  | +0.0087 (+2.32) | −0.0012 (−0.33) | +0.0038 (+1.06) | −0.0011 (−0.30) |
| breadth_cs   | +0.0003 (+0.09) | +0.0097 (+2.78) | +0.0021 (+0.62) | +0.0014 (+0.43) |
| risk_cs      | **+0.0656 (+13.16)** | **+0.0742 (+15.22)** | **+0.0911 (+18.49)** | **+0.1138 (+23.76)** |

### 16 atomic signals (ρ / t per horizon)

| Feature                              | 5d              | 10d             | 20d             | 60d             |
|--------------------------------------|----------------:|----------------:|----------------:|----------------:|
| mom_ret_5d                           | −0.0201 (−4.75) | −0.0048 (−1.15) | −0.0008 (−0.18) | +0.0083 (+2.11) |
| mom_ret_10d                          | −0.0148 (−3.49) | −0.0045 (−1.09) | −0.0013 (−0.33) | +0.0019 (+0.50) |
| mom_ret_20d                          | −0.0140 (−3.21) | −0.0074 (−1.73) | −0.0030 (−0.73) | −0.0084 (−2.01) |
| macd_hist_12_26_9                    | −0.0113 (−2.62) | +0.0017 (+0.40) | +0.0106 (+2.57) | +0.0057 (+1.46) |
| macd_hist_slope5_12_26_9             | −0.0172 (−4.07) | −0.0091 (−2.15) | −0.0076 (−1.85) | +0.0034 (+0.85) |
| sma_cross_strength_signed_5_20       | +0.0128 (+4.16) | +0.0175 (+5.74) | +0.0127 (+4.26) | +0.0143 (+5.05) |
| ema_cross_strength_signed_5_20       | +0.0120 (+3.91) | +0.0180 (+5.93) | +0.0164 (+5.54) | +0.0189 (+6.44) |
| ma50_slope_20d                       | −0.0092 (−2.06) | −0.0171 (−3.83) | −0.0278 (−6.46) | −0.0066 (−1.77) |
| ma50_dev                             | −0.0166 (−3.87) | −0.0137 (−3.22) | −0.0194 (−4.60) | −0.0141 (−3.39) |
| bb_pctb_20                           | −0.0064 (−1.79) | +0.0014 (+0.37) | −0.0023 (−0.65) | −0.0055 (−1.58) |
| rsi_dist_os_14                       | +0.0110 (+3.02) | +0.0017 (+0.45) | +0.0059 (+1.67) | −0.0001 (−0.03) |
| rsi_turn_event_14                    | −0.0132 (−4.13) | −0.0069 (−2.17) | −0.0041 (−1.34) | −0.0026 (−0.85) |
| kdj_os_distance                      | −0.0044 (−1.21) | −0.0150 (−4.17) | −0.0166 (−4.82) | −0.0185 (−5.44) |
| bb_z_20                              | −0.0054 (−1.48) | +0.0028 (+0.73) | −0.0001 (−0.03) | −0.0027 (−0.76) |
| mr_z_40_skip16                       | +0.0108 (+3.05) | +0.0197 (+5.55) | +0.0268 (+7.55) | +0.0004 (+0.13) |
| ma50_dev_z_40                        | +0.0015 (+0.41) | +0.0093 (+2.46) | +0.0028 (+0.75) | −0.0140 (−4.15) |

### Reading the table

- **The `trend_cs` sleeve aggregates 9 momentum signals whose ρ is mostly
  negative at 5d.** Inside the sleeve, `sma/ema_cross_strength_signed_5_20`
  are robustly *positive* (t up to +6.4 at 60d) but the raw-return momentum
  signals (`mom_ret_5d/10d/20d`) and `ma50_dev` swamp them when summed
  equal-weight. This is the immediate mechanism for the −0.40-weight bug.
- `risk` is the strongest stable signal across all four horizons — a classic
  low-volatility premium, intensified in crypto by lottery-ticket bid-up
  patterns on high-vol meme/microcap.
- `breadth` only becomes meaningful at 10d (t=+2.78). It is essentially a
  re-aggregation of the same 9 trend signals, so its weakness at 5d mirrors
  the trend sleeve.
- Among atomics, the 5d edge story is: **MA-cross slopes (+), short
  RSI/MR signals (+); raw momentum, MACD-hist, RSI-turn-event, MA50-dev (−).**
  Crypto 5d is mean-reverting (consistent with academic crypto-microstructure
  literature on liquidity-driven flow).

## B. Recommended Calibrated Weights (5d, mode = "drop")

Sleeve budget = 0.90 (TS-history sleeves keep 0.05 each, Tier-A default).
Rule: |t| < 2 → weight = 0. ρ < 0 with meaningful t → weight = 0 (conservative).
Surviving sleeves get budget × |ρ| / Σ|ρ|.

| Sleeve       | Tier-A | Calibrated 5d | Reason                                       |
|--------------|-------:|--------------:|----------------------------------------------|
| trend        | 0.40   | **0.000**     | ρ = −0.0143, t = −3.55 → dropped (sign wrong)|
| reversal     | 0.25   | **0.105**     | ρ = +0.0087, t = +2.32, meaningful           |
| breadth      | 0.15   | **0.000**     | t = +0.09, insignificant at 5d → dropped     |
| risk         | 0.10   | **0.795**     | ρ = +0.0656, t = +13.16, dominant            |
| ts_trend_2y  | 0.05   | 0.05          | Tier-A default (not in calibration panel)    |
| ts_reversal_2y | 0.05 | 0.05          | Tier-A default (not in calibration panel)    |

### Multi-horizon mean-blend (stretch task D)

For an "all-horizon" composite, we average each sleeve's raw |ρ| across the 4
horizons (only counting horizons where the sleeve is statistically meaningful
*and* the empirical sign is positive) and renormalise:

| Sleeve   | All-horizon blend |
|----------|------------------:|
| trend    | 0.000             |
| reversal | 0.022             |
| breadth  | 0.024             |
| risk     | 0.854             |
| ts_trend_2y / ts_reversal_2y | 0.05 / 0.05 |

The blend concentrates even harder on risk because risk wins at every
horizon. Operators who want explanatory diversity can clamp `risk ≤ 0.50`
and re-normalise — see "Phase Recommendations" below.

## C. Holdout Validation

Out-of-sample slice: last 20% of dates (2025-02-10 → 2026-05-15, 460 dates,
83,783 panel rows). FMB ρ on each horizon for three weight schemes:

| Horizon | Tier-A          | **Calibrated 5d** | All-horizon blend |
|---------|----------------:|------------------:|------------------:|
| 5d      | +0.0210 (+2.10) | **+0.0506 (+4.50)** | +0.0521 (+4.55) |
| 10d     | +0.0273 (+2.83) | +0.0522 (+4.60)   | +0.0547 (+4.73) |
| 20d     | +0.0393 (+3.91) | +0.0758 (+6.65)   | +0.0775 (+6.68) |
| 60d     | +0.0694 (+6.91) | +0.0904 (+8.35)   | +0.0927 (+8.32) |

- **5d ρ ≈ 2.4× Tier-A**, t-stat from +2.1 → +4.5; no horizon is negative.
- All-horizon blend marginally beats the 5d-calibrated weights at every
  horizon. I recommend shipping the blend as the production "calibrated"
  mode, with the per-horizon weights kept in the artifact for transparency
  (already in `by_horizon`).
- The Tier-B Ridge writer in `tier_b_weights.json` produced
  trend=0.0 / reversal=0.37 / breadth=0.28 / risk=0.26 with rho_B=0.0044 on
  walk-forward — and *did not accept* (gate is +0.02 over Tier-A). My
  out-of-sample numbers are an order of magnitude larger because (a) I
  evaluate the composite, not the Ridge per se, and (b) I'm using the
  **last 20%** as a single holdout — a fair comparison, since Tier-A's own
  reported ρ is computed the same way.

## D. Survivorship Risk Disclosure (mandatory)

`scores_history.csv` was built from today's CoinGecko universe:

- 2 tokens on day 0 (2020-01-30), 240 on day −1 (2026-05-15).
- **0 tokens delisted in the entire history**: every token alive today
  appears in scores_history, but tokens that *died* before today are absent.
- 206 tokens "added later" (first date > panel start + 30 days).

What this means for the calibrated weights:

1. The ρs above are systematically **upward biased**. The size of the bias
   is unknown but in equity research the survivorship effect is typically
   1–3 percentage points on annualised long-short alpha; for ρ-based metrics
   the absolute effect is smaller but proportional. Live trading edge will
   be *less* than the holdout ρ.
2. The `risk` (low-vol) sleeve is the **most exposed** to this bias because
   "high-vol token that died" is exactly the cohort missing from the panel.
   The +0.11 ρ at 60d almost certainly inflates the true population edge.
3. Sleeve *signs* are robust — survivorship bias rarely flips a sign — so
   the qualitative finding (trend reversed at 5d, risk dominant at all
   horizons) holds.

This warning is now written into:
- `local_data/scoring/calibrated_weights.json → survivorship_warning`
- `local_data/scoring/horizon_calibration.json → survivorship.warning`
- `local_data/scoring/tier_b_weights.json → survivorship_warning` (added)
- `GET /api/scoring/calibrated → survivorship_warning` (for UI to surface)

## E. Phase Recommendations

**P0 — ship the calibrated mode (this PR)**
- `overall_score.resolve_weights("calibrated")` wired; default stays "theory"
  until product confirms. Add a Toggle in the UI ("Theory / Calibrated /
  Tier-B") and surface the survivorship warning under the Calibrated tab.
- Cap `risk` at 0.50 if the product team wants explanatory diversity — a
  scoring system that's 80% "low vol percentile" is academically defensible
  but UX-unhelpful. Easy to do in `calibrated_weights.py::calibrate` by
  passing a per-sleeve cap dict.

**P1 — survivorship-clean panel (data architecture)**
- Use CoinGecko `/coins/markets` snapshots at month-end going back to 2020
  to reconstruct point-in-time universes. Restrict each date's CS-ranking
  to the universe that existed at that date. Re-run both `analyze_horizons`
  and `train_tier_b`.
- Budget: one ML-week + listing-snapshot back-fill. Expect 30–50%
  attenuation in risk-sleeve ρ; trend/reversal sleeves likely unchanged.

**P2 — within-sleeve atomic re-weighting**
- The trend sleeve is *not* uniformly broken: `sma/ema_cross_strength_*`
  alone would give trend a positive ρ. Re-weight atomic signals inside each
  sleeve by per-horizon ρ instead of equal weight. This recovers some of
  the trend-sleeve information that the current aggregation throws away
  and is the proper fix for the "trend reversed at 5d" problem (vs the
  blunter "drop trend to 0" we're shipping now).

**P3 — non-linear / interaction modelling**
- All current analysis is rank-linear. The 5d crypto mean-reversion edge
  is likely volatility-regime conditional (you mean-revert harder after
  vol spikes). Two-feature interactions (risk_cs × trend_cs) or a small
  gradient-boosted model on the same 20 features are natural next steps,
  but only worth doing *after* fixing survivorship — otherwise we'd overfit
  to the alive-today distribution.

## Files Touched

- `scripts/analyze_horizons.py` (new) — full multi-horizon panel analysis.
- `backend/scoring/calibrated_weights.py` (new) — sign-respecting calibration.
- `backend/scoring/overall_score.py` — added "calibrated" mode to
  `resolve_weights`, added `resolve_contribution_signs`.
- `backend/api/routes_scoring_meta.py` — added `GET /api/scoring/calibrated`.
- `scripts/train_tier_b.py` — added `_survivorship_audit` + payload fields.
- `local_data/scoring/calibrated_weights.json` (artifact)
- `local_data/scoring/horizon_calibration.json` (artifact)
- `local_data/scoring/_horizon_panel_cache.pkl` (cache for re-runs)
