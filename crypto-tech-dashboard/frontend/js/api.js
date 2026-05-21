// Frontend API client — thin fetch wrappers around the five routers.

const API = (() => {
    async function _get(path) {
        const resp = await fetch(path, { headers: { "accept": "application/json" } });
        if (!resp.ok) {
            const txt = await resp.text();
            throw new Error(`GET ${path} -> ${resp.status} ${txt.slice(0, 200)}`);
        }
        return resp.json();
    }

    async function _post(path, body) {
        const opts = { method: "POST", headers: { "content-type": "application/json" } };
        if (body !== undefined) opts.body = JSON.stringify(body);
        const resp = await fetch(path, opts);
        if (!resp.ok) {
            const txt = await resp.text();
            throw new Error(`POST ${path} -> ${resp.status} ${txt.slice(0, 200)}`);
        }
        return resp.json();
    }

    return {
        listTokens: (asset_class = "") => _get(
            asset_class ? `/api/tokens?asset_class=${encodeURIComponent(asset_class)}` : "/api/tokens"
        ),
        getToken: (id) => _get(`/api/tokens/${encodeURIComponent(id)}`),
        getOhlc: (id, days = 365) => _get(`/api/ohlc/${encodeURIComponent(id)}?days=${days}`),
        getIndicators: (id, days = 365) => _get(`/api/indicators/${encodeURIComponent(id)}?days=${days}`),
        getFamily: (id, family, days = 365, params = null) => {
            let url = `/api/indicators/${encodeURIComponent(id)}/${encodeURIComponent(family)}?days=${days}`;
            if (params) {
                for (const k of Object.keys(params)) {
                    const v = params[k];
                    if (v == null || v === "") continue;
                    url += `&${encodeURIComponent(k)}=${encodeURIComponent(v)}`;
                }
            }
            return _get(url);
        },
        listScores: (sort_by = "trend", limit = 0) => _get(`/api/scores?sort_by=${sort_by}&limit=${limit}`),
        getScore: (id) => _get(`/api/scores/${encodeURIComponent(id)}`),
        getRankings: (sort_by = "trend", limit = 20, asset_class = "") => {
            let url = `/api/rankings?sort_by=${sort_by}&limit=${limit}`;
            if (asset_class) url += `&asset_class=${encodeURIComponent(asset_class)}`;
            return _get(url);
        },
        getBacktest: (id, fast = 5, slow = 20) => _get(`/api/backtest/${encodeURIComponent(id)}?fast=${fast}&slow=${slow}`),
        getSparklines: (ids, days = 30) => _get(`/api/sparklines?ids=${encodeURIComponent(ids.join(","))}&days=${days}`),
        getMarketOverview: (id) => _get(`/api/market_overview/${encodeURIComponent(id)}`),    // R8-1C
        getDataCoverage: (id) => _get(`/api/data-coverage/${encodeURIComponent(id)}`),         // R8-1B.2
        // R8-2B: indicator robustness
        getRobustnessSummary: (asset_class = "crypto") => _get(`/api/indicator-robustness?asset_class=${encodeURIComponent(asset_class)}`),
        getRobustnessDetail: (strategy, asset_class = "crypto") => _get(`/api/indicator-robustness/${encodeURIComponent(strategy)}?asset_class=${encodeURIComponent(asset_class)}`),
        postRobustnessRecompute: (asset_class = "crypto") => _post(`/api/indicator-robustness/recompute?asset_class=${encodeURIComponent(asset_class)}`),
        // R8-2C: scoring explainers
        getScoringExplainers: () => _get("/api/scoring/explainer"),
        // R8-4A: Tier-B status (used by the Overall hero card banner)
        getTierBStatus:       () => _get("/api/scoring/tier_b"),
        // Audit + MIT peer-review: calibrated weights status w/ Sharpe verdict
        getCalibratedStatus:  () => _get("/api/scoring/calibrated"),
        getSystemStatus: () => _get("/api/system/status"),
        getSystemHealth: () => _get("/api/system/health"),
        getRefreshProgress: () => _get("/api/system/refresh-progress"),
        postRefresh: (full = false) => _post(`/api/system/refresh?full=${full ? "true" : "false"}`),
    };
})();
