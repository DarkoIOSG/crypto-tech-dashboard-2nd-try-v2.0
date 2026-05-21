# MIT ML 教授 peer-review — 最终裁定: **MAJOR REVISIONS**

Reviewer: CSAIL, financial ML. Scope: `/tmp/ML_OPTIMIZATION.md` + four code artifacts under `crypto-tech-dashboard/`.

---

## TL;DR

1. The qualitative finding (risk sleeve dominates, trend sleeve has wrong sign at 5d) is **directionally credible** — t-stats on risk are large enough to survive any reasonable correction. But the **quantitative claims are not yet trustworthy**: t-stats are inflated by overlapping forward returns, the headline "2.4x holdout improvement" cannot be reproduced from the committed code, and the recommended weights are derived from a panel that contains the holdout.
2. Making "calibrated" the production default on these numbers is **unsafe**. Survivorship + leakage + 80% concentration on a single (low-vol) factor in a panel with zero delistings is a textbook recipe for live blow-up.
3. **Accept the diagnostic, reject the prescription.** Ship calibrated as opt-in (already done — good), keep default = theory, and require the revisions in §7 before any default change.

---

## 1. 方法论审查

| 论点 | ML scientist 声称 | 我的判断 | 严重度 |
|---|---|---|---|
| FMB t = ρ̄ / (sd/√T) | Honest cross-sectional read | **NOT Newey-West.** `_fmb_rho` (analyze_horizons.py L166-185) computes `t = mean / (sd/√T)` assuming per-date ρ are iid. With h=5d forward returns, ρ_t and ρ_{t+1} share 4/5 of their y-axis → AR(1) ≈ 0.8. Effective N is ~ T/h, not T. Correct SE inflates by √((1+ρ)/(1-ρ)) ≈ 3x for h=5d, ~4x for h=10d, ~6x for h=20d, ~11x for h=60d (rule of thumb). | HIGH |
| Trend ρ=−0.0143, t=−3.55 | Statistically significant wrong-sign | After NW(h-1) correction the t is roughly **−1.2 at 5d**. **Not significant at single-test level, let alone after multiple comparisons.** Dropping the trend sleeve on this evidence is overreach. | HIGH |
| Risk t up to +23.76 (60d) | Dominant signal | Even with NW deflation by 11x → t ≈ +2.2. Still positive, but the "ρ=+0.114" is also survivorship-inflated (see §3). The certainty implied by t=+23 is illusory. | HIGH |
| 16 features × 4 horizons | Implicit single-test framing | **80 tests.** Bonferroni α=0.05/80 → t-critical ≈ 3.16. Reversal (t=+2.32), MACD (t=−2.62), breadth-10d (t=+2.78), several MAs all fail. After NW correction, only the *risk sleeve* and the MA-cross atomics survive a family-wise correction. The report's "meaningful" threshold |t|≥2.0 is too loose given 80 simultaneous tests. | HIGH |
| Per-date ρ then mean | "More honest" | Better than pooled, but still **cluster-non-robust** in the token dimension: a token appears ~2,289 times. Per-date FMB controls cross-sectional contemporaneous correlation but not within-token serial correlation in residuals. Need either **double-clustered SE (date, token)** or a **block bootstrap on overlapping date-blocks**. | MEDIUM |
| Pooled `_spearman_with_t` (`panel_t`) | Auxiliary | This formula assumes 243k iid obs. Wildly overstates significance; should be removed from the artifact, not reported alongside FMB. | LOW (cosmetic) |

---

## 2. 数据 leakage 风险

**This is the most serious problem in the submission.**

a) **The Section-C "holdout" table is not reproducible from the repo.** I grep'd every script under `/scripts/` and `/backend/` for the numbers 0.0210, 0.0506, 0.0521 and for "last 20%" / "0.8" date splits. `analyze_horizons.py` builds the panel and computes FMB ρ on the *full* sample only — it never carves out a holdout. `train_tier_b.py` does walk-forward but yields ρ_A ≈ 0.0044, nothing close to +0.0210. **The holdout claim is currently undocumented and unverifiable.** This alone is grounds for rejection of the recommendation; reviewers cannot accept headline performance from off-repo notebook arithmetic.

b) **Even if such a holdout were run, it is in-sample for the weights.** `calibrated_weights.py::calibrate` reads `horizon_calibration.json`, which was built from the *entire* panel including 2025-02-10 → 2026-05-15. The ρ used to size sleeves already saw the holdout. Re-evaluating the resulting weights on that same window is **circular**. The improvement +0.021 → +0.051 partly measures fit-to-its-own-test-set.

c) **Honest walk-forward requires expanding/rolling weight recomputation.** At each test date t, ρ̂(feature, fwd_h) should use only data ≤ t − h (to avoid leakage from the look-ahead embedded in forward returns themselves). The current pipeline never does this for the calibrated weights — it does for Tier-B Ridge. The asymmetry must be fixed before the head-to-head is meaningful.

---

## 3. Survivorship 处理充分性

The disclosure is honest (visible in artifact `survivorship_warning`, audit fields, route payload). What's missing:

- **The bias is asymmetric across sleeves.** Risk gets the biggest lift (high-vol tokens that died are missing), reversal gets a smaller lift, trend's negative-ρ may even be *attenuated* (a dying token has a momentum crash → if it were in the panel, momentum's negative 5d ρ would likely be *more* negative, but its surviving-only sample suppresses this). **You cannot justify a 79.5% risk weight on a panel with 0 delistings.** The cohort that would push back on low-vol-premium claims — namely high-vol tokens that subsequently died — is precisely the cohort missing.
- **P1 (point-in-time universe rebuild) should be a blocker for changing the default, not a follow-up.** Equity-research rule of thumb is that survivorship inflates long-short α by 1–3pp annually, but in *crypto microcap* with zero recorded delistings over a 6-year sample, the bias is qualitatively larger. Ship this as P0 if anyone wants calibrated weights to drive real allocation.
- "Sleeve signs are robust — survivorship rarely flips signs" is **true in the literature but unverified here.** Show me a bootstrap dropping the bottom-decile-by-marketcap from each historical CS rank and re-running FMB.

---

## 4. "Drop trend to 0" 是否过激

**Yes — this is a methodological own-goal.** The author's own atomic-signal table shows:
- `sma_cross_strength_signed_5_20`: ρ +0.013 to +0.014, t up to +5.05 across horizons
- `ema_cross_strength_signed_5_20`: ρ +0.012 to +0.019, t up to +6.44

These are the only two atomic signals with **stable, sign-consistent positive ρ at every horizon**. They are also the only trend signals that survive even a naive Bonferroni. By forcing the *sleeve average* through a |t|≥2 gate, the calibration kills the strongest stable signal in the panel.

The author's own P2 ("within-sleeve atomic re-weighting") is the correct fix. Shipping P0 = "drop trend sleeve" before P2 is **strictly dominated** by P2: it discards positive information to fix a sign problem that exists only in the equal-weight aggregation, not in the underlying signals. P2 must be done before, not after, ratifying the calibrated weights.

---

## 5. 默认 mode 建议

**Keep default = "theory".** Reasoning:

- Holdout numbers are leakage-contaminated (§2).
- Risk weight of 0.795/0.854 in a 0-delisting panel is not defensible (§3).
- Trend-sleeve drop is dominated by P2 (§4).
- Plan literally specifies theory as default; PM/Plan deviation requires evidence quality that this submission does not yet provide.
- The product cost of keeping theory as default is small (Toggle is already in place; calibrated is exposed). The cost of shipping calibrated as default and discovering in live deployment that the low-vol factor was a survivorship artifact is large.

If the author wants calibrated to become default, the bar should be: (i) leakage-clean walk-forward repro of the +0.021→+0.051 number; (ii) survivorship-clean panel; (iii) Sharpe / turnover / capacity numbers, not just ρ.

---

## 6. ML scientist 漏掉的几点

1. **No token-level clustering.** Per-date FMB controls cross-sectional dependence; nothing controls within-token dependence. Double-cluster or token-block bootstrap. Likely deflates risk-sleeve t by another 30–50%.
2. **Horizon choice (5/10/20/60) is undefended.** Why not 1/3/7/30? With 4 choices × 16 atomic, the testing space is large. Pre-register horizons or run the analysis on a randomly sampled grid.
3. **TS-history sleeves are sidelined by assertion, not analysis.** "Not in the calibration panel" — but `ts_trend_2y` is a within-token percentile and can be evaluated against forward returns. Right now they are held at 0.05 each by fiat, which is fine, but should be acknowledged as **untested**, not as "Tier-A default."
4. **No Sharpe / turnover / capacity / decay metrics.** Cross-sectional IC is necessary but not sufficient. A 79% risk-weighted composite is a slow-rotating low-vol portfolio; CS-ρ does not tell us if it survives trading costs or capacity constraints in microcap crypto. Report deciles → long-short P&L → annualized Sharpe at minimum.
5. **No regime split.** Crypto 5d mean-reversion is well-known to be vol-regime-conditional (Makarov-Schoar, Liu-Tsyvinski). Show ρ in high-vol vs low-vol regimes; the calibrated weights may differ dramatically.
6. **Reservoir of forking paths.** Multiple choices (mode=drop vs flip, |t|≥2, 4 horizons, mean-blend definition that filters by sign+significance) are made in code without sensitivity analysis. A garden of forking paths inflates effective false-positive rate well beyond Bonferroni.
7. **The `ridge_fit` in `_fit_sleeve_ridge` uses a single 80/20 random split for α selection — random across time = leakage.** Same bug as §2 in miniature.

---

## 7. 给 ML scientist 的具体修改清单

Priority-ordered. Items P0a–P0d block any change of default mode.

**P0a — Reproducible holdout (BLOCKER).** Add a function `evaluate_weights_walkforward(panel, weights_fn, horizon)` to `analyze_horizons.py` that, for each test date t, computes weights from `data[date < t − h]` and evaluates composite-vs-fwd_h ρ on `data[date == t]`. Aggregate over the last 20% of dates. Persist `holdout_walkforward.json` with per-date ρ for Tier-A, Calibrated-5d, Blend. The numbers in Section C as currently written are not in the repo.

**P0b — Newey-West / HAC SE.** In `_fmb_rho`, replace `t = mean / (sd/√T)` with a Newey-West SE using lag = h − 1. Add `fmb_t_nw` alongside `fmb_t`. Re-issue the Section A table with NW-t. Expect risk to remain highly significant; expect trend at 5d to drop to |t| ≈ 1–1.5 and lose its "wrong-sign significant" status.

**P0c — Token-clustered SE / block bootstrap.** Implement a token-and-date double-cluster SE (Cameron-Gelbach-Miller) or a moving-block bootstrap over (date-block of length h, all tokens). Report bootstrapped 95% CI for every sleeve ρ. Any sleeve whose CI includes 0 after NW + cluster + Bonferroni-on-80-tests should not enter the weight rule.

**P0d — Multiple-comparison gate.** Replace `|t| ≥ 2.0` in `_meaningful` with either Bonferroni (`|t| ≥ 3.16` over 80 tests) or BH-FDR at q=0.10 across the (feature × horizon) grid. Document the chosen procedure.

**P1a — Within-sleeve atomic re-weighting (the real fix for trend).** Before dropping the trend sleeve, build a horizon-specific trend composite weighting `sma_cross_strength_*` and `ema_cross_strength_*` heavily and downweighting `mom_ret_*`. Re-evaluate sleeve ρ under this reweighting. If trend then shows positive sign at 5d, P0 "drop trend to 0" is invalidated — the sleeve was never bad, the equal-weight aggregation was. This is the author's own P2 and should be promoted to P1.

**P1b — Survivorship-clean panel.** Rebuild `scores_history.csv` from point-in-time CoinGecko snapshots before promoting calibrated to default. Re-run the entire analysis. Expected: risk-sleeve ρ at 60d drops from +0.11 toward +0.05–0.07. The 80%-risk recommendation will likely become a 40–50%-risk recommendation.

**P2 — Cap risk weight.** Until P1b is done, hard-cap `risk ≤ 0.50` in `calibrated_weights.py::calibrate` via a kwarg, default on. Anything above 0.50 is academically defensible only after the survivorship fix.

**P2b — Portfolio metrics.** Implement decile long-short backtest on top of the composite. Report annualized return, Sharpe, max DD, turnover, and capacity-at-1bp-impact for Tier-A, Calibrated, Blend. CS-ρ alone is not a release gate.

**P2c — Regime split.** Stratify FMB ρ by realised BTC 30d vol quartile. Disclose regime-conditional weights.

**P3 — Remove pooled `panel_rho` / `panel_t` from artifacts.** They are misleading at scale 243k. Keep FMB only.

**P3b — Fix `_fit_sleeve_ridge` α-tuning.** Replace the 80/20 random split with a time-respecting walk-forward CV.

---

**Final note to the author.** Diagnostically this is good work — the trend-sign issue and the risk-sleeve dominance are real findings and worth pursuing. But the leap from "diagnostic" to "production weight recommendation with default-mode change" is too aggressive given the SE assumptions, the unverifiable holdout, and the survivorship panel. Run the P0 items, redo the head-to-head, and bring it back. The default mode should not move until then.
