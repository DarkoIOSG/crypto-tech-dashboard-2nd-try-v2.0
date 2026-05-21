"""R8-2C: human-readable explainers for the 3 score families.

Served by GET /api/scoring/explainer. The frontend hits this once at
boot, caches it, and shows the relevant block in the click-to-open
modal when a `?` info-mark in any score card is clicked.

Phase-2 item 1c ("add explanation of the computation logic to the chart").
"""

from __future__ import annotations


TREND_EXPLAINER = {
    "title": "Trend Score",
    "one_line": "Blended SMA / EMA / MACD / momentum signals, cross-sectionally ranked to 0-100.",
    "formula_md": (
        "Trend = equal-weighted mean of 9 signal percentiles, "
        "then cross-sectional rank-percentile across today's universe.\n\n"
        "Higher = the token is showing stronger momentum than its peers right now."
    ),
    "signal_table": [
        {"key": "mom_ret_10d",                    "label": "Momentum (10d)",            "weight": 1.0},
        {"key": "mom_ret_20d",                    "label": "Momentum (20d)",            "weight": 1.0},
        {"key": "macd_hist_12_26_9",              "label": "MACD Histogram",            "weight": 1.0},
        {"key": "macd_hist_slope5_12_26_9",       "label": "MACD Histogram Slope (5d)", "weight": 1.0},
        {"key": "sma_cross_strength_signed_5_20", "label": "SMA Cross Strength (5/20)", "weight": 1.0},
        {"key": "ema_cross_strength_signed_5_20", "label": "EMA Cross Strength (5/20)", "weight": 1.0},
        {"key": "ma50_slope_20d",                 "label": "MA50 Slope (20d)",          "weight": 1.0},
        {"key": "ma50_dev",                       "label": "MA50 Deviation",            "weight": 1.0},
        {"key": "bb_pctb_20",                     "label": "Bollinger %B (20)",         "weight": 1.0},
    ],
    "strengths": [
        "Captures persistent trends across multiple timeframes",
        "Robust against a single indicator's false signal",
        "Cross-sectional ranking insulates from regime shifts",
    ],
    "weaknesses": [
        "Lags inflection points by ~5-10 days",
        "False signals in choppy / sideways markets",
        "Treats all 9 signals equally — could over-weight correlated ones",
    ],
    "interpretation": {
        "above_70": "Strong uptrend across most signals — momentum continuation likely.",
        "33_70":    "Mixed signals — wait for confirmation.",
        "below_33": "Weak / downtrending — avoid long entries.",
    },
}


REVERSAL_EXPLAINER = {
    "title": "Reversal Score",
    "one_line": "Blended RSI / KDJ / Bollinger / mean-reversion signals — high score = oversold setup.",
    "formula_md": (
        "Reversal = signed-weighted mean of 7 signal percentiles "
        "(some negated so 'low' becomes 'high'), then cross-sectional "
        "rank-percentile.\n\n"
        "Higher = the token is showing a stronger mean-reversion / "
        "oversold setup vs its peers right now."
    ),
    "signal_table": [
        {"key": "rsi_dist_os_14",   "label": "RSI Oversold Distance (14)",      "weight":  1.0},
        {"key": "rsi_turn_event_14", "label": "RSI Turn Event (14)",             "weight":  1.0},
        {"key": "kdj_os_distance",   "label": "KDJ Oversold Distance",           "weight":  1.0},
        {"key": "bb_z_20",           "label": "Bollinger Z-Score (inverted)",    "weight": -1.0},
        {"key": "mr_z_40_skip16",    "label": "Mean Reversion Z (40, skip 16)",  "weight":  1.0},
        {"key": "ma50_dev_z_40",     "label": "MA50 Deviation Z (40)",           "weight": -1.0},
        {"key": "mom_ret_5d",        "label": "Negative Momentum (5d)",          "weight": -1.0},
    ],
    "strengths": [
        "Identifies oversold bounce candidates",
        "Multi-indicator agreement reduces single-signal noise",
        "Sign-flipped signals turn 'bearish extremes' into 'reversal setup'",
    ],
    "weaknesses": [
        "Reversal calls during strong trends often fail",
        "Crypto can stay oversold longer than fundamentals justify",
        "Requires a 'turn event' trigger before high-conviction entries",
    ],
    "interpretation": {
        "above_70": "Strong oversold / mean-reversion candidate — watch for trigger.",
        "33_70":    "Mid-range — no clear reversal setup.",
        "below_33": "Trending or extended above mean — not a reversal play.",
    },
}


OVERALL_EXPLAINER = {
    "title": "Overall Composite Score (Tier A)",
    "one_line": "Single headline blend: 40% Trend + 25% Reversal + 15% Breadth + 10% Risk + 10% 2y History.",
    "formula_md": (
        "Overall = 0.40·Trend + 0.25·Reversal + 0.15·Breadth + 0.10·Risk + "
        "0.05·Trend_TS_2y + 0.05·Reversal_TS_2y\n\n"
        "All six sleeves are 0-100 cross-sectional percentiles within the "
        "asset class (crypto vs US-stock partitioned separately). Weights "
        "from finance-theory priors (Liu/Tsyvinski 2021; Russell/Engle 2010); "
        "Tier B in Phase 2D will replace them with Ridge-regressed weights "
        "trained on forward 5-day return."
    ),
    "signal_table": [
        {"key": "trend",          "label": "Trend",            "weight": 0.40},
        {"key": "reversal",       "label": "Reversal",         "weight": 0.25},
        {"key": "breadth",        "label": "Signal Breadth",   "weight": 0.15},
        {"key": "risk",           "label": "Risk (low vol)",   "weight": 0.10},
        {"key": "ts_trend_2y",    "label": "Trend TS 2y",      "weight": 0.05},
        {"key": "ts_reversal_2y", "label": "Reversal TS 2y",   "weight": 0.05},
    ],
    "strengths": [
        "Single headline number — no Trend/Reversal interpretation needed",
        "Risk-adjusted via inverse vol penalty",
        "Captures long-history strength via 2y time-series sleeves",
        "Cross-section partitioned by asset class — crypto and stocks don't pollute each other's percentile space",
    ],
    "weaknesses": [
        "Weights are theory-driven, not empirically learned (Tier B fixes this)",
        "Breadth weighting may over-discount when most signals correlate",
        "Inverse-vol Risk sleeve favors low-momentum stable coins",
    ],
    "interpretation": {
        "above_70": "Strong composite setup — multi-sleeve alignment.",
        "33_70":    "Mixed — at least one sleeve drags the others down.",
        "below_33": "Weak across the composite — consider passing.",
    },
}


# UX-audit Phase-2 final review: 4 missing sleeve explainers. Hero card
# displays 6 sleeve rows (trend / reversal / breadth / risk / ts_trend_2y /
# ts_reversal_2y) but only 3 had a `?` info-mark. Analyst writing morning
# note hit a dead-end on the other 4. Now every sleeve has a story.

BREADTH_EXPLAINER = {
    "title": "Signal Breadth",
    "one_line": "Percentage of the 9 trend signals that are currently positive, then ranked cross-sectionally.",
    "formula_md": "breadth = 100 × (# trend signals > 0) / 9, then percentile-rank across today's universe.",
    "weight_in_overall": 0.15,
    "strengths": [
        "Penalises one-or-two-signal trend setups; rewards broad agreement",
        "Robust to any single indicator failing",
    ],
    "weaknesses": [
        "Highly correlated with the trend sleeve itself",
        "Weakest statistical edge at 5d horizon (t≈0 in our calibration)",
    ],
    "interpretation": {
        "above_70": "Most trend signals aligned — high-conviction trend regime.",
        "30_70": "Mixed agreement — wait for breadth to widen before sizing up.",
        "below_30": "Most signals disagree — chop / regime transition.",
    },
}

RISK_EXPLAINER = {
    "title": "Risk (low volatility)",
    "one_line": "Inverse of 20-day annualised realised volatility, cross-sectionally ranked.",
    "formula_md": "risk_raw = −vol_20d; risk_cs = percentile-rank across universe today. Higher score = LOWER volatility.",
    "weight_in_overall": 0.10,
    "strengths": [
        "Captures the well-documented low-vol premium that holds in crypto across every horizon (5d to 60d, t up to +24)",
        "Sleeve with the strongest empirical edge in our backtest panel",
    ],
    "weaknesses": [
        "Survivorship-biased: 'high-vol dying token' cohort is missing from the panel; live edge will be less",
        "A score that's 80% low-vol on its own would over-concentrate the portfolio (see calibrated mode disclaimer)",
    ],
    "interpretation": {
        "above_70": "Top quintile low-volatility token — defensive characteristics.",
        "30_70": "Mid-vol — typical crypto majors.",
        "below_30": "High realised vol — meme / micro-cap behaviour.",
    },
}

TS_TREND_2Y_EXPLAINER = {
    "title": "Trend TS 2y",
    "one_line": "Where this token's CURRENT trend score sits in its OWN rolling 2-year history.",
    "formula_md": "Percentile rank of today's trend_score against the same token's distribution over the trailing 730 days.",
    "weight_in_overall": 0.05,
    "strengths": [
        "Captures rare-strength outliers that cross-sectional ranking misses",
        "Per-token baseline so a token strong by ITS own history is rewarded even if average across universe",
    ],
    "weaknesses": [
        "Returns 50 (neutral) for tokens with <730 days history — about 100/240 tokens",
        "Not directly in the calibration panel; weight stays at Tier-A 0.05 default",
    ],
    "interpretation": {
        "above_70": "Today's trend reading is in the top 30% of this token's own 2-year history.",
        "30_70": "Trend in normal range for this token.",
        "below_30": "Token's own historical trend was usually stronger than today.",
    },
}

TS_REVERSAL_2Y_EXPLAINER = {
    "title": "Reversal TS 2y",
    "one_line": "Where this token's CURRENT reversal score sits in its OWN rolling 2-year history.",
    "formula_md": "Percentile rank of today's reversal_score against the same token's distribution over the trailing 730 days.",
    "weight_in_overall": 0.05,
    "strengths": [
        "Same per-token baseline benefit as trend TS 2y",
        "Flags 'historically rare' reversal setups for the specific token",
    ],
    "weaknesses": [
        "Same short-history neutral-fill (~100/240 tokens)",
        "Not directly in the calibration panel; weight stays at Tier-A 0.05 default",
    ],
    "interpretation": {
        "above_70": "Today's reversal score is in the top 30% of this token's own 2-year history.",
        "30_70": "Reversal in normal range for this token.",
        "below_30": "Token's own history shows this is a tame reversal setup.",
    },
}

ALL_EXPLAINERS = {
    "trend":          TREND_EXPLAINER,
    "reversal":       REVERSAL_EXPLAINER,
    "overall":        OVERALL_EXPLAINER,
    "breadth":        BREADTH_EXPLAINER,
    "risk":           RISK_EXPLAINER,
    "ts_trend_2y":    TS_TREND_2Y_EXPLAINER,
    "ts_reversal_2y": TS_REVERSAL_2Y_EXPLAINER,
}
