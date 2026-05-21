// R8-2B: indicator robustness table + click-through per-token detail
// Phase-2 item 6.

const RobustnessPanel = (() => {
    const STRATEGY_RULES = {
        rsi_oversold_30_50: "RULE: enter long when RSI(14) < 30 (oversold); exit when RSI(14) > 50. Indicator family: RSI mean reversion. Backtest uses next-day execution and 5 bps commission.",
        macd_signal_cross: "RULE: enter long when MACD line crosses above its signal line; exit when MACD crosses below signal. MACD = EMA12 - EMA26; Signal = EMA(MACD, 9). Backtest uses next-day execution and 5 bps commission.",
        kdj_oversold_cross: "RULE: enter long when K crosses above D while both are below 20 (oversold turn); exit when K crosses below D while both are above 80. Requires real high/low bars, so close-only tokens are excluded or NaN-suppressed.",
        bollinger_lower_band: "RULE: enter long when close touches or falls below the lower Bollinger band; exit when price returns to the middle band. Bands use SMA20 ± 2 standard deviations by default.",
        sma_golden_cross: "RULE: enter long when SMA(5) > SMA(20); exit / go flat when SMA(5) <= SMA(20). This is the simple moving-average golden-cross strategy.",
        ema_golden_cross: "RULE: enter long when EMA(5) > EMA(20); exit / go flat when EMA(5) <= EMA(20). EMA reacts faster than SMA because recent prices receive higher weight.",
        momentum_breakout: "RULE: enter long when 20-day return is positive; exit when 20-day return is zero or negative. This tests simple trend-following continuation.",
        zscore_reversion: "RULE: enter long when price z-score is below -2 (stretched below mean); exit when z-score rises above 0. This tests mean-reversion from statistically cheap levels.",
        price_appreciation: "RULE: enter long when 20-day return > 10% AND volume z-score > 2; exit when 5-day return < 0. This tests high-momentum, volume-confirmed appreciation.",
    };

    const RELIABILITY_TITLES = {
        reliable: "Reliable: median Sharpe ≥ 0.5, at least 60% of tokens have positive Sharpe, and the worst token Sharpe is not below -1.0. This means the rule worked broadly, not just on one winner.",
        caveats: "Caveats: the strategy has some signal but does not clear the full reliable gate. Usually median Sharpe is 0.2-0.5 or % positive is 50-60%; use only with confirmation from other indicators.",
        unreliable: "Unreliable: median Sharpe / breadth / worst-case behavior fails the gate. Treat this indicator as descriptive context, not a standalone trading rule.",
        unknown: "Reliability unavailable: robustness cache did not return enough aggregate statistics for this strategy.",
    };

    const SUMMARY_CELL_TITLES = {
        median_sharpe: "Median annualized Sharpe across eligible tokens. Per-token formula: sqrt(365) × mean(daily_strategy_return) / std(daily_strategy_return) for crypto, with next-day fill and 5 bps commission; then take the median across tokens.",
        pct_positive: "Percentage of eligible tokens with Sharpe > 0. Formula: 100 × positive_sharpe_tokens / n_tokens. Higher means the indicator worked across many names rather than one outlier.",
        best: "Best token for this strategy by annualized Sharpe. Useful for seeing where the rule historically had the strongest fit.",
        worst: "Worst token for this strategy by annualized Sharpe. Large negative values show where the rule can fail badly.",
        n: "Number of tokens included in this strategy's universe-wide backtest. Tokens need sufficient OHLCV history; close-only data can remove KDJ or volume-dependent calculations.",
    };

    const DETAIL_COL_TITLES = {
        token: "Token ticker / CoinGecko id. Click a row to load that token in the main dashboard.",
        sharpe: "Annualized Sharpe for this strategy on this token: sqrt(365) × mean(daily_strategy_return) / std(daily_strategy_return), after next-day execution and 5 bps commission.",
        cagr: "Compound annual growth rate of the strategy equity curve on this token. Formula: final_equity^(365 / backtest_days) - 1 for crypto.",
        max_dd: "Maximum drawdown: worst peak-to-trough loss of the strategy equity curve. Formula: min(equity / rolling_peak - 1). More negative means deeper historical pain.",
        trades: "Number of round-trip trades produced by this rule. Very low trade count means the Sharpe is less statistically stable.",
        win_rate: "Percentage of completed trades with positive return. Formula: 100 × winning_trades / total_trades.",
    };

    function _esc(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function _reliabilityBadge(rel) {
        const title = _esc(RELIABILITY_TITLES[rel] || RELIABILITY_TITLES.unknown);
        if (rel === "reliable")   return `<span class="rel-badge rel-ok" title="${title}">reliable</span>`;
        if (rel === "caveats")    return `<span class="rel-badge rel-mid" title="${title}">caveats</span>`;
        if (rel === "unreliable") return `<span class="rel-badge rel-bad" title="${title}">unreliable</span>`;
        return `<span class="rel-badge" title="${title}">—</span>`;
    }

    function _fmtSharpe(v) {
        if (v == null || Number.isNaN(v)) return "—";
        return v.toFixed(2);
    }

    function _fmtPct(v) {
        if (v == null || Number.isNaN(v)) return "—";
        return `${v.toFixed(1)}%`;
    }

    async function renderSummary(asset_class) {
        const tbody = document.querySelector("#robustness-table tbody");
        const detail = document.getElementById("robustness-detail");
        if (!tbody) return;
        tbody.innerHTML = "";
        if (detail) { detail.hidden = true; detail.innerHTML = ""; }

        const data = await API.getRobustnessSummary(asset_class).catch(() => null);
        if (!data || !data.available || !data.strategies) {
            tbody.innerHTML = `<tr><td colspan="7" class="muted">No robustness data yet for asset_class=${asset_class}. Run POST /api/indicator-robustness/recompute.</td></tr>`;
            return;
        }

        Object.entries(data.strategies).forEach(([name, s]) => {
            const tr = document.createElement("tr");
            tr.classList.add("rob-row");
            tr.setAttribute("data-strategy", name);

            const rule = STRATEGY_RULES[name] || (s.label || name);
            tr.title = "Click to open per-token results for this strategy.";
            tr.innerHTML = `
                <td class="strat-name" title="${_esc(rule)}">${name}</td>
                <td class="num" title="${_esc(SUMMARY_CELL_TITLES.median_sharpe)}">${_fmtSharpe(s.median_sharpe)}</td>
                <td class="num" title="${_esc(SUMMARY_CELL_TITLES.pct_positive)}">${_fmtPct(s.pct_positive)}</td>
                <td class="num" title="${_esc(SUMMARY_CELL_TITLES.best)}">${s.best ? `${s.best.symbol || s.best.cg_id}: ${_fmtSharpe(s.best.sharpe)}` : "—"}</td>
                <td class="num" title="${_esc(SUMMARY_CELL_TITLES.worst)}">${s.worst ? `${s.worst.symbol || s.worst.cg_id}: ${_fmtSharpe(s.worst.sharpe)}` : "—"}</td>
                <td class="num" title="${_esc(SUMMARY_CELL_TITLES.n)}">${s.n_tokens || 0}</td>
                <td>${_reliabilityBadge(s.reliability)}</td>
            `;
            tr.addEventListener("click", () => renderDetail(name, asset_class));
            tbody.appendChild(tr);
        });
    }

    async function renderDetail(strategy_name, asset_class) {
        const detail = document.getElementById("robustness-detail");
        if (!detail) return;
        detail.hidden = false;
        detail.innerHTML = `<div class="muted">Loading ${strategy_name} details…</div>`;

        const d = await API.getRobustnessDetail(strategy_name, asset_class).catch(() => null);
        if (!d || !d.per_token) {
            detail.innerHTML = `<div class="muted">No detail cache for ${strategy_name}</div>`;
            return;
        }

        // Top + worst summary, then sortable table of all tokens
        let html = `
            <div class="rob-detail-head">
                <strong>${strategy_name}</strong>
                <span class="muted">${d.label || ""}</span>
                <span class="muted">${d.n_tokens} tokens · ${_reliabilityBadge(d.reliability)}</span>
            </div>
            <table class="rob-detail-table">
                <thead><tr>
                    <th title="${_esc(DETAIL_COL_TITLES.token)}">Token</th>
                    <th title="${_esc(DETAIL_COL_TITLES.sharpe)}">Sharpe</th>
                    <th title="${_esc(DETAIL_COL_TITLES.cagr)}">CAGR</th>
                    <th title="${_esc(DETAIL_COL_TITLES.max_dd)}">Max DD</th>
                    <th title="${_esc(DETAIL_COL_TITLES.trades)}">Trades</th>
                    <th title="${_esc(DETAIL_COL_TITLES.win_rate)}">Win Rate</th>
                </tr></thead>
                <tbody>
        `;
        d.per_token.forEach(r => {
            html += `<tr data-token="${r.cg_id}">
                <td class="tok" title="${_esc(DETAIL_COL_TITLES.token)}">${r.symbol || r.cg_id}</td>
                <td class="num" title="${_esc(DETAIL_COL_TITLES.sharpe)}">${_fmtSharpe(r.sharpe)}</td>
                <td class="num" title="${_esc(DETAIL_COL_TITLES.cagr)}">${(r.cagr * 100).toFixed(1)}%</td>
                <td class="num" title="${_esc(DETAIL_COL_TITLES.max_dd)}">${(r.max_dd * 100).toFixed(1)}%</td>
                <td class="num" title="${_esc(DETAIL_COL_TITLES.trades)}">${r.n_trades}</td>
                <td class="num" title="${_esc(DETAIL_COL_TITLES.win_rate)}">${(r.win_rate * 100).toFixed(0)}%</td>
            </tr>`;
        });
        html += `</tbody></table>`;
        detail.innerHTML = html;

        // Click-through to load that token in the main view.
        detail.querySelectorAll("tr[data-token]").forEach(row => {
            row.addEventListener("click", () => {
                const tk = row.getAttribute("data-token");
                if (tk && typeof window.selectTokenFromAnywhere === "function") {
                    window.selectTokenFromAnywhere(tk);
                }
            });
        });
    }

    return { renderSummary, renderDetail };
})();
