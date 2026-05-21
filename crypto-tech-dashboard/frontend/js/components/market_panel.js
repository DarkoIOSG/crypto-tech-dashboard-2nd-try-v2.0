// R8-1C: market-info panel — 5 tiles between token selector and score detail.
// Renders rank / mcap / 24h vol / 30d avg vol / liquidity venue.

const MarketPanel = (() => {
    // Format large dollar values: $1.42T / $79.5K / $2.85B / $850M
    function _fmtUSD(v) {
        if (v == null || Number.isNaN(v)) return "—";
        const abs = Math.abs(v);
        const sign = v < 0 ? "-" : "";
        if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
        if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
        if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(2)}M`;
        if (abs >= 1e3)  return `${sign}$${(abs / 1e3).toFixed(2)}K`;
        return `${sign}$${abs.toFixed(2)}`;
    }
    function _fmtNum(v) {
        if (v == null || Number.isNaN(v)) return "—";
        const abs = Math.abs(v);
        if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
        if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
        if (abs >= 1e3) return `${(v / 1e3).toFixed(2)}K`;
        return v.toFixed(2);
    }
    function _fmtRank(v) {
        if (v == null || Number.isNaN(v)) return "—";
        return `#${Math.round(v)}`;
    }

    async function render(id) {
        const overview = await API.getMarketOverview(id).catch(() => null);
        const root = document.getElementById("market-cap-panel");
        if (!root) return;
        if (overview == null) {
            root.hidden = true;
            return;
        }
        root.hidden = false;
        const tiles = {
            "mcap-rank": _fmtRank(overview.market_cap_rank),
            "mcap-value": _fmtUSD(overview.market_cap),
            "vol-24h": _fmtUSD(overview.total_volume_24h),
            "vol-30d": _fmtNum(overview.avg_volume_30d),
            "liquidity-source": (overview.liquidity && overview.liquidity.source_tag) || "—",
        };
        for (const [el_id, val] of Object.entries(tiles)) {
            const el = document.getElementById(el_id);
            if (el) el.textContent = val;
        }
        // Tooltip on liquidity tile: explain the venue
        const liqEl = document.getElementById("liquidity-source");
        if (liqEl && overview.liquidity && overview.liquidity.source_tag) {
            const src = overview.liquidity.source_tag;
            liqEl.title = src === "coingecko"
                ? "Close-only data from CoinGecko (no exchange OHLC available)."
                : `Latest OHLC sourced from ${src}. 30d volume is the rolling average from this venue.`;
        }
    }

    return { render };
})();
