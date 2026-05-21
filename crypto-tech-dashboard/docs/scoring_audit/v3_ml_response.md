# ML Optimization v2 — Response to MIT Peer-Review

**Author:** ML scientist (revision)
**Date:** 2026-05-15
**Status:** v1 received MAJOR REVISIONS. This is the response.
**Scope:** all of MIT's BLOCKER and Major critiques re-addressed with fully
reproducible code.

All numbers below come from the committed code:
- `scripts/analyze_horizons.py` (rewritten v2)
- `backend/scoring/calibrated_weights.py` (rewritten v2)
- Artifacts: `local_data/scoring/horizon_calibration.json` (schema_v2),
  `holdout_walkforward.json` (new), `calibrated_weights.json` (v2 schema).

Reproduce: `python3 scripts/analyze_horizons.py && python3 -m backend.scoring.calibrated_weights`.

## TL;DR

| MIT critique | Status | Resolution |
|---|---|---|
| B1: holdout unreproducible | **confirmed** | New `evaluate_oos_weights()` with chronological 80/20 split now in repo. Cutoff = 2025-02-10. Numbers below are reproducible. |
| B2: constructive leakage (full-panel weights) | **confirmed** | Train-only weight path added. Artifact now carries both `weights_full_sample` (explanatory) and `weights_train_only` (deployable). |
| B3: t-stats not NW-adjusted | **confirmed** | Newey-West HAC SE with lag = h-1 implemented. Risk 60d t collapses 23.76 → 4.23 (still highly significant). Trend 5d t collapses -3.55 → **-2.08** (MIT predicted ≈-1.2; reality less dramatic but still loses Bonferroni). |
| B4: multiple comparisons (80 tests) | **confirmed** | Bonferroni gate |t_nw| ≥ 3.16 added. Only `risk_cs` (all horizons) and `rsi_turn_event_14` (5d) survive family-wise. MA-cross atomics survive at 10d only. |
| M5: survivorship promoted to blocker | **partially confirmed** | Sensitivity analysis added (`weights_sensitivity_risk_minus_30pct`, `weights_train_only_haircut`). With only one sleeve surviving the gate, weights are insensitive to the haircut — but absolute live edge is materially lower. |
| M6: atomic re-weighting before drop | **strongly confirmed** | New `compute_atomic_weighted_sleeve("trend",...)` keeps the SMA/EMA-cross babies, gives a **positive** holdout rho at every horizon ≤ 20d (vs equal-weight sleeve which is borderline). The "drop trend to 0" decision is dominated. |
| m7: keep default = theory | **agreed** | No change to default mode. |
| m8: cluster bootstrap, Sharpe/turnover, ridge chrono split | **all done** | 200-rep token-cluster bootstrap, decile long-short Sharpe/turnover, ridge α picked by chronological 80/20 CV. **Sharpe finding is bad news for calibrated mode — see §G.** |

**New punchline that v1 missed:** even though calibrated weights have higher
cross-sectional Spearman rho than theory weights on the leakage-clean
holdout (+0.052 vs +0.021 at 5d, holdout NW-t = 2.56 vs 1.22), the actual
decile-long-short Sharpe of the calibrated portfolio is *lower than theory's
at 5d (–0.40 vs +0.58) and at 60d (+0.37 vs +0.76)*. CS-IC ≠ deployable
alpha. This is exactly the warning MIT m8 articulated and v1 failed to test.
**This finding alone justifies retiring the recommendation to ship
calibrated as default. See §H for the new verdict.**

## A. Newey-West-adjusted Multi-Horizon Table (full sample, schema_v2)

Method: per-date Spearman ρ across `cg_id`; mean across dates; SE via
Newey-West with Bartlett kernel, lag = h−1 (the AR-order built into
h-day overlapping forward returns). `t_raw` is the v1 ρ/(sd/√T) figure;
`t_nw` is the corrected one. `*` = passes Bonferroni at α=0.05/80 (|t|≥3.16).

### Sleeve table (the headline)

| Sleeve | 5d ρ / t_raw / **t_nw** | 10d | 20d | 60d |
|---|---|---|---|---|
| trend_cs    | −0.0143 / −3.55 / **−2.08** | −0.0041 / −1.02 / −0.46 | −0.0032 / −0.82 / −0.29 | +0.0046 / +1.20 / +0.28 |
| reversal_cs | +0.0087 / +2.32 / **+1.38** | −0.0012 / −0.33 / −0.15 | +0.0038 / +1.06 / +0.40 | −0.0011 / −0.30 / −0.08 |
| breadth_cs  | +0.0003 / +0.09 / **+0.05** | +0.0097 / +2.78 / +1.30 | +0.0021 / +0.62 / +0.23 | +0.0014 / +0.43 / +0.11 |
| risk_cs     | +0.0656 / +13.16 / **+7.59*** | +0.0742 / +15.22 / +6.33* | +0.0911 / +18.49 / +5.40* | +0.1138 / +23.76 / **+4.23*** |

Effects of NW correction:
- Risk sleeve: NW deflation factor ranges from 1.7× (5d) to 5.6× (60d). All
  4 horizons still pass Bonferroni. MIT's directional prediction (risk
  remains dominant after correction) is confirmed; MIT's magnitude
  prediction (deflation up to 11×) was a slight overestimate.
- Trend 5d: t goes −3.55 → −2.08. Survives single-test |t|≥2 but **fails
  Bonferroni 3.16**. MIT's "real |t| ≈ 1.2 → not significant" was too
  pessimistic; trend 5d remains marginally significant on its own but is
  not a survivor of family-wise correction.
- Reversal 5d (t=+2.32) and Breadth 10d (t=+2.78) both **drop to |t|<1.5**
  under NW and lose their single-test significance, confirming MIT B3.

### Atomic-signal NW-t (key rows)

| Atomic                                | 5d ρ / t_nw  | 10d ρ / t_nw    | 20d ρ / t_nw    | 60d ρ / t_nw    | Bonf? |
|---|---|---|---|---|---|
| mom_ret_5d                            | −0.0201/−3.10 | −0.0048/−0.65 | −0.0008/−0.09 | +0.0083/+0.91 | no |
| macd_hist_slope5_12_26_9              | −0.0172/−2.54 | −0.0091/−1.14 | −0.0076/−0.93 | +0.0034/+0.56 | no |
| sma_cross_strength_signed_5_20        | +0.0128/+2.70 | +0.0175/+3.18 | +0.0127/+1.99 | +0.0143/+1.95 | 10d* |
| ema_cross_strength_signed_5_20        | +0.0120/+2.51 | +0.0180/+3.20 | +0.0164/+2.51 | +0.0189/+2.22 | 10d* |
| rsi_turn_event_14                     | −0.0132/**−5.68*** | −0.0069/−3.51* | −0.0041/−2.67 | −0.0026/−2.24 | 5d/10d* |
| kdj_os_distance                       | −0.0044/−0.73 | −0.0150/−2.16 | −0.0166/−2.25 | −0.0185/−2.16 | no |
| ma50_dev                              | −0.0166/−2.26 | −0.0137/−1.37 | −0.0194/−1.42 | −0.0141/−0.65 | no |

Bonferroni survivors across the 80-test family (|t_nw| ≥ 3.16):
- `risk_cs` at every horizon (5/10/20/60d).
- `rsi_turn_event_14` at 5d (t=−5.68) and 10d (t=−3.51) — a wrong-sign mean
  reversion signal that v1 essentially missed.
- `sma_cross_strength_signed_5_20` and `ema_cross_strength_signed_5_20` at
  10d only.

Everything else MIT flagged (Reversal sleeve, MACD-hist, Breadth-10d) fails
Bonferroni and most fails |t|≥2 too. MIT critique B4 is **confirmed in full**.

## B. Train-only-calibrated weights (the deployable ones)

Split: chronological, `train < 2025-02-10`. Train dates = 1838, holdout
dates = 460. Weights fit on train-slice FMB ρ with NW t-stats, threshold
|t_nw|≥2.0, drop-mode (zero out sign-wrong or insignificant sleeves).

### Train-only sleeve stats (5d horizon, the headline)

| Sleeve | rho_train | t_nw_train | passes |t|≥2 | passes Bonferroni |
|---|---|---|---|---|
| trend_cs    | −0.0190 | −2.46 | yes (but wrong sign → dropped) | no |
| reversal_cs | +0.0111 | +1.51 | no | no |
| breadth_cs  | −0.0008 | −0.12 | no | no |
| risk_cs     | +0.0690 | +7.25 | yes | yes |

**Only `risk_cs` survives. So weights_train_only(5d) = {risk: 0.90, ts_*:
0.05 + 0.05, everything else: 0}.** Same answer at 10d/20d/60d. This is the
exact same concentration as v1, but now properly justified on train-only,
NW-corrected stats. The Bonferroni-gated weights are identical (risk is the
only Bonferroni survivor among sleeves anyway).

### Mixed-horizon vote (the "all-horizon blend")

Every horizon votes "only risk is meaningful and positive" → blend weight
on risk = LEARNABLE_BUDGET = 0.90. Same conclusion. The artifact field
`all_horizon_blend_weights` records this.

## C. Walk-forward / chronological holdout (the actually reproducible C)

The v1 Section C table was the major BLOCKER. Replacement: for each
horizon h:
1. Split panel at 2025-02-10.
2. Fit cal weights on train only.
3. Composite = Σ w_s · sleeve_value_s on the holdout slice.
4. Per-date Spearman vs `fwd_{h}d`, mean across dates, NW-t with lag h−1.

| Horizon | Cal (train-only) rho / **t_nw**_hold | Theory rho / **t_nw**_hold | Δrho |
|---|---|---|---|
| 5d  | **+0.0519 / +2.56** | +0.0211 / +1.22 | +0.031 |
| 10d | +0.0544 / +1.91     | +0.0274 / +1.20 | +0.027 |
| 20d | +0.0772 / +1.84     | +0.0393 / +1.18 | +0.038 |
| 60d | +0.0921 / +1.47     | +0.0694 / +1.29 | +0.023 |

So the **CS-IC headline survives** the leakage-clean redo: calibrated rho
> theory rho at every horizon, and the 5d advantage is nominally
significant (NW-t = +2.56) while theory's is not (NW-t = +1.22). The
+0.021 → +0.051 figure from v1 Section C is reproduced. But two caveats:

1. NW-t on the holdout itself is only meaningfully > 2 at 5d. At 10d/20d
   the calibrated-vs-theory edge is positive but not significant.
2. The Bonferroni variant gives identical weights — same answer.
3. Section G below shows this CS-IC advantage *does not translate into
   long-short Sharpe*. This is the most important finding in v2.

## D. Survivorship sensitivity analysis

Cluster-bootstrap (200 reps, every-5th-date subsample, resampling tokens
with replacement) gives 95% CIs for sleeve ρ at 5d and 60d:

| Sleeve | 5d boot_mean / 95% CI | 60d boot_mean / 95% CI |
|---|---|---|
| trend_cs    | −0.0147 / [−0.027, −0.002] | +0.0054 / [−0.015, +0.024] |
| reversal_cs | +0.0092 / [−0.004, +0.021] | −0.0018 / [−0.018, +0.015] |
| breadth_cs  | −0.0001 / [−0.012, +0.012] | +0.0020 / [−0.016, +0.019] |
| risk_cs     | **+0.0649 / [+0.053, +0.076]** | **+0.1153 / [+0.090, +0.142]** |

Risk's CI is far from zero even after cluster-bootstrapping over tokens;
this is genuine token-cross-sectional signal in the surviving universe.
**But the cluster bootstrap cannot fix the missing-cohort problem** (dead
tokens are not in the universe to bootstrap from).

### Forced-haircut sensitivity (risk ρ × 70%)

`weights_sensitivity_risk_minus_30pct(5d)` artifact field: even after
shrinking the risk-sleeve |ρ| by 30%, **the weights are still risk=0.90,
everything else=0** — because the other sleeves are still under the
NW-t≥2 gate. The sensitivity test demonstrates how *little* the weight rule
can absorb the survivorship correction: it has only one sleeve to fall
back on. The only way the calibrated weight rule would diversify under
realistic survivorship is if at least one *other* sleeve gained
significance — which is the opposite of what survivorship correction does
(it shrinks every sleeve's edge, especially risk).

### Per-sleeve expected live haircut (encoded in `calibrated_weights.json`)

Default haircuts: risk 40%, reversal 20%, breadth 15%, trend 10%
(asymmetric exposure to the missing-high-vol-dying-token cohort). With
DEFAULT_SURVIVORSHIP_HAIRCUT applied: same answer (risk=0.90) because the
other sleeves are 0 anyway. **The haircut machinery is now in place but
the gate is too coarse to use it productively.** This corroborates MIT M5:
the calibrated weights are *not robust* to plausible survivorship
adjustments — they always concentrate on whichever sleeve passes the
absolute t-gate, and right now that's only risk.

## E. Within-sleeve atomic re-weighting — saving the trend baby

Per MIT M6, the *real* fix for trend isn't "drop sleeve" but "drop wrong-
sign atomics, keep babies". `compute_atomic_weighted_sleeve("trend", h)`
implements this: gate atomic-signal NW-t ≥ 2.0, drop sign-wrong, weight
the survivors by |ρ|.

| h | Atomic weights (train-only) | Holdout re-weight ρ / t_nw | Equal-weight ρ / t_nw | Δ |
|---|---|---|---|---|
| 5d | sma_cross 0.51, ema_cross 0.49 | **+0.0094 / +1.01** | +0.0050 / +0.35 | +0.0044 |
| 10d | sma_cross 0.49, ema_cross 0.51 | **+0.0125 / +1.08** | +0.0088 / +0.51 | +0.0037 |
| 20d | ema_cross 1.00 | **+0.0154 / +1.05** | +0.0135 / +0.54 | +0.0020 |
| 60d | (none survives train gate) | n/a | n/a | n/a |

**The re-weighted trend sleeve has positive holdout ρ at every horizon ≤
20d** — vs the v1 decision to set trend weight = 0. Equal-weight
sleeve-level ρ at 5d on holdout is +0.005, *not negative* (the −0.014
in-sample number flipped sign on holdout — a 1.4σ swing — meaning the
trend-sleeve "wrong-sign edge" v1 keyed on was substantially in-sample
noise). Atomic re-weighting modestly improves on this, but holdout NW-t ≈
1.0 means the trend sleeve is **statistically indistinguishable from zero
either way**. The "kill the trend sleeve" recommendation in v1 was based
on overestimating both the magnitude and stability of the wrong-sign
issue. M6 is confirmed: drop is dominated by re-weight, and re-weight is
itself only weakly differentiated from "keep" given the small effect.

## F. Cluster bootstrap robustness check

Already shown in §D. Summary:
- Risk sleeve CIs are far from zero (5d: [+0.053, +0.076]; 60d: [+0.090,
  +0.142]) → token-clustered SE confirms risk-sleeve significance.
- Trend / Reversal / Breadth CIs straddle zero at both 5d and 60d → not
  cluster-significant.

MIT m1 ("likely deflates risk-sleeve t by another 30-50%") is **not
borne out for risk**: the bootstrap mean ρ matches the per-date FMB ρ
almost exactly, and the CI half-width is small relative to the mean. The
NW correction already does most of the work; cluster bootstrap adds
little extra deflation. For the other sleeves the bootstrap confirms what
NW already showed (CI through zero).

## G. Simulated long-short Sharpe / turnover — the kill shot

`simulate_long_short()`: per-day, on the holdout slice, long the top
quintile of the composite, short the bottom quintile, hold for h days,
average h-day forward log-return. Annualised Sharpe = mean/sd ×
√(365/h). Turnover = average symmetric-difference fraction in
top/bottom-quintile membership day over day.

| Horizon | Strategy   | Sharpe (annual) | Turnover (daily) | Mean h-day log-ret |
|---|---|---|---|---|
| 5d  | Calibrated (risk 0.90) | **−0.40** | 0.178 | −0.0007 |
| 5d  | Theory (40/25/15/10)   | **+0.58** | 0.466 | +0.0009 |
| 60d | Calibrated (risk 0.90) | **+0.37** | 0.175 | +0.0095 |
| 60d | Theory (40/25/15/10)   | **+0.76** | 0.467 | +0.0179 |

This is the result that decides the deployment question. Two facts to sit
with:

1. **Calibrated has higher cross-sectional rank correlation but lower
   (in fact negative at 5d) long-short P&L Sharpe.** CS-IC is a rank
   statistic; it ignores the magnitude / sign asymmetry that drives
   actual returns. The +0.052 holdout ρ at 5d says "low-vol tokens *tend
   to* outperform high-vol tokens on rank". The −0.40 Sharpe at 5d says
   "the few high-vol tokens that go up go up *enormously*, and shorting
   them blows the P&L". This is the classic low-vol-anomaly-fails-out-of-
   sample pattern in crypto microcap, where the short side has a heavy
   right tail (meme runs, listing pumps) and the long side has a thin
   left tail.

2. **Turnover is lower for calibrated (0.18 vs 0.47)**, which would be
   nice in production — but the higher-Sharpe strategy already has the
   acceptable turnover the theory weights produce.

This *was the specific scenario* MIT m4 warned about: CS-IC necessary but
not sufficient, real metric is Sharpe / capacity / decay. **v1's headline
was the wrong metric.**

## H. 最终修订 recommendation

**Verdict: retire the recommendation to ship calibrated mode as a
production default. Keep the calibrated *mode* in the code as an
analytic/research toggle, but with a stronger UI disclaimer and no
suggestion to switch the default away from theory.**

Specific actions:

1. **Default mode stays "theory"** (already the case — keep it that way).
   MIT m7 agreed; v2 confirms.

2. **Calibrated mode**: keep the route + the UI toggle, but the surfaced
   recommendation in the UI / report should now say: *"Calibrated weights
   maximise cross-sectional rank correlation on a leakage-clean holdout
   but produce lower (or negative at 5d) long-short Sharpe than theory
   weights. Do not deploy as a trading rule. Useful as an explanatory
   indicator only."* The artifact already has the survivorship warning;
   add the Sharpe finding to the same payload.

3. **Trend sleeve**: do NOT drop. The v1 P0 "drop trend to 0" was the
   strongest claim of v1 and §A/§E show it was based on (a) a t-stat that
   shrinks below Bonferroni after NW, and (b) an in-sample sign that
   flipped on the holdout. Keep equal-weight trend in theory mode. If we
   later want a calibrated trend that doesn't throw babies out, the
   atomic-reweighting machinery (`compute_atomic_weighted_sleeve`) is in
   the code, ready for an opt-in re-weight that keeps SMA/EMA-cross.

4. **Survivorship rebuild is now the gating P0** for any future
   recalibration: without delisted-token panel rebuilding, the calibrated
   weights will keep concentrating on risk because no other sleeve will
   pass the gate, and risk's edge is the most survivorship-inflated of
   all. P1b in v1 must become P0 before there's any point retrying this
   calibration. Estimated work: 1–2 ML-weeks for point-in-time
   CoinGecko snapshot reconstruction.

5. **Use Sharpe (or decile L-S P&L) as a release gate**, not CS-IC, going
   forward. This is the principle from MIT m4. `simulate_long_short()`
   is in `analyze_horizons.py` and should be re-run after any weight
   change.

### Was the v1 work wasted?

No. The artifact pipeline (NW correction, train-only weights, holdout
walk-forward, cluster bootstrap, atomic-reweight, Sharpe sim) is now
permanently in `analyze_horizons.py` and is the right framework for any
future weight-rule research. The diagnostic findings are still useful:
risk-sleeve dominance in CS-IC is real, trend has babies inside, the
panel is severely survivorship-biased. We've just learned to not let CS-
IC alone justify a default-mode change.

### What I disagree with in MIT's review

- B3 magnitude: MIT predicted risk-sleeve t would deflate to ≈+2.2 at
  60d after NW. Reality is +4.23 — still very strong. The Bartlett-kernel
  NW with lag 59 leaves more signal than MIT's deflation rule of thumb
  suggested. Bonferroni-corrected, risk still passes by a wide margin.
- B3 magnitude (trend): MIT predicted trend 5d t ≈ −1.2 (not significant).
  Reality is −2.08 — still significant single-test but not Bonferroni.
  So MIT was directionally right (NW kills the v1 −3.55) but the
  magnitude was overestimated.
- m1 cluster effect: MIT expected another 30–50% deflation of risk-sleeve
  t from cluster bootstrap. Did not happen; bootstrap mean ≈ FMB mean,
  CI half-width small.

### Files modified in v2

- `scripts/analyze_horizons.py` — full rewrite. New: `_fmb_rho` returns
  both raw and NW t-stat; `evaluate_oos_weights`, `_chronological_split`,
  `_cluster_bootstrap_rho`, `compute_atomic_weighted_sleeve`,
  `simulate_long_short`. Random-CV ridge replaced with chronological CV.
- `backend/scoring/calibrated_weights.py` — full rewrite. New: `train_only`
  / `full_sample` modes; Bonferroni t-threshold; survivorship haircut;
  sensitivity-analysis fields; atomic-reweighted-trend payload.
  Backward-compatible `load_calibrated_weights()` and
  `load_contribution_signs()` preserved for callers in `overall_score.py`
  and `routes_scoring_meta.py`.
- Artifacts overwritten: `horizon_calibration.json` (schema_v2 with
  NW + train-only + Bonferroni flags + cluster bootstrap),
  `calibrated_weights.json` (v2 with five weight variants +
  atomic_reweighted_trend), `holdout_walkforward.json` (new file:
  walk-forward holdout numbers per horizon, atomic-reweight per horizon,
  Sharpe simulation).
- No git commit (per instructions).

### Reproducibility

```
cd crypto-tech-dashboard
source venv/bin/activate
python3 scripts/analyze_horizons.py     # ~7 min (uses cached panel)
python3 -m backend.scoring.calibrated_weights
```

Every number in this report comes out of the two artifacts written by
those two commands. The cluster bootstrap uses `seed=13+h`,
`date_subsample=5`, `n_boot=200`; the chronological split uses
`TRAIN_FRAC=0.80`. All deterministic given the input data.
