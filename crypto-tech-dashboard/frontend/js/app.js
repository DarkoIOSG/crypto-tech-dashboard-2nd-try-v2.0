// Main controller — orchestrates token selection, chart rendering, score
// display, ranking sidebar, and time-axis synchronisation.

(() => {
    const FAMILIES = [
        "sma_cross", "ema_cross", "macd", "rsi", "rsi_mr", "kdj",
        "bollinger", "volume_spike", "momentum", "mean_reversion",
        "zscore_ma", "price_appreciation",
    ];

    let candleCtx = null;
    const indicatorCharts = {};   // family -> Chart instance
    let equityChart = null;       // P1-G: backtest equity curve chart instance
    let equitySeries = null;
    let priceOverlaySeries = null;
    let isSyncing = false;        // global lock to prevent event loops
    let currentToken = null;
    let currentAssetClass = "crypto";   // R8-1D: active sidebar tab
    // Token catalogue for the searchable combobox.
    let tokenCatalog = [];        // [{id, symbol, name, has_ohlcv}, ...] scoped to currentAssetClass
    // Phase 3.5: full cross-asset catalog used only for refresh progress
    // labels — the progress bar shows a stocks ticker while the crypto tab
    // is active (or vice-versa), and we need its display name regardless of
    // which tab is currently selected. Refreshed at the same time as
    // tokenCatalog (cheap: 1 extra GET on /api/tokens with no filter).
    let tokenCatalogAll = [];
    let dropdownMatches = [];     // current filtered slice
    let dropdownActiveIdx = -1;   // for keyboard nav
    const CLOSE_ONLY_TIP =
        "DATA WARNING: this token is close-only in our local OHLCV cache. " +
        "Definition: CoinGecko supplies daily close prices but no real open/high/low/volume from the integrated spot-exchange waterfall. " +
        "Synthetic bars are stored as open = high = low = close and volume = 0. " +
        "Calculation impact: KDJ needs true high/low and Volume Spike needs true volume, so those signals are set to NaN and removed from score averages instead of fabricating values. " +
        "Interpretation impact: Trend can still use close-based returns / moving averages, but Reversal is less reliable because one of its oversold inputs is unavailable. " +
        "Typical cause: no liquid spot pair on Binance, OKX, Bybit, Gate.io, Coinbase, Kraken, KuCoin, or Bitstamp.";

    async function init() {
        // R8-1D: parse #tab=us-stock or #tab=crypto from URL hash so deep
        // links are shareable. UX-audit final: also reads #token= below.
        const initParams = (window._parseHashInit = (function () {
            const out = {};
            const raw = (location.hash || "").replace(/^#/, "");
            for (const part of raw.split("&")) {
                const m = part.match(/^([a-z_]+)=([^&]+)$/i);
                if (m) out[m[1]] = decodeURIComponent(m[2]);
            }
            return out;
        })());
        if (initParams.tab === "us-stock" || initParams.tab === "crypto") {
            currentAssetClass = initParams.tab;
        }

        await loadTokens();
        await loadRankings();
        await loadSystemStatus();
        wireCombobox();
        wireParamControls();
        wireMobileDrawer();
        wireAssetClassTabs();
        wireThemeToggle();
        document.getElementById("rank-mode").addEventListener("change", loadRankings);
        document.getElementById("refresh-btn").addEventListener("click", onRefreshClick);
        document.getElementById("backtest-run").addEventListener("click", onBacktestRun);

        // UX-audit final: prefer #token= URL hash so a copied link lands the
        // user on the same token. Falls through to the asset-class default
        // (BTC for crypto, CRCL for stocks) when no hash present.
        // Phase 3 Module 8 (PM): hashToken match is case-insensitive so
        // pasted #token=BITCOIN or #token=crcl both resolve.
        const hashParams = _parseHash();
        const hashToken = hashParams.token;
        const preferred = currentAssetClass === "us-stock" ? "CRCL" : "bitcoin";
        let fromHash = null;
        if (hashToken) {
            const wanted = String(hashToken).toLowerCase();
            fromHash = tokenCatalog.find(
                t => String(t.id).toLowerCase() === wanted && t.has_ohlcv
            ) || null;
            if (!fromHash) {
                // Phase 3 Module 8 (PM): surface a non-blocking toast so the
                // user knows their pasted #token=... did not resolve, instead
                // of silently swapping to BTC/CRCL.
                if (typeof Toast !== "undefined") {
                    Toast.show(
                        `Token "${hashToken}" not found. Showing ${preferred} ` +
                        `— try BTC / ETH / SOL / CRCL.`,
                        { kind: "warn", duration: 5000 }
                    );
                } else {
                    console.warn(
                        `[app] hash token "${hashToken}" not in catalog; ` +
                        `falling back to ${preferred}`
                    );
                }
            }
        }
        const first = fromHash
                   || tokenCatalog.find(t => t.id === preferred && t.has_ohlcv)
                   || tokenCatalog.find(t => t.has_ohlcv);
        if (first) {
            selectToken(first.id);
        }

        // R8-2B: indicator robustness table — load cached summary
        // for the current asset_class.
        if (typeof RobustnessPanel !== "undefined") {
            RobustnessPanel.renderSummary(currentAssetClass);
        }

        // R8-2B: expose selectToken globally so the robustness detail
        // table can click-through to a token from anywhere.
        window.selectTokenFromAnywhere = (tk) => selectToken(tk);

        // R8-2C: wire .info-mark[data-explainer] clicks to open the
        // explainer modal.
        if (typeof ExplainerModal !== "undefined") {
            ExplainerModal.wire();
        }

        // R8-4A / Audit P1: render Tier-B status banner on the Overall hero
        // card so users see whether the composite is theory-driven (default)
        // or data-driven (only if accept gate passed).
        renderTierBBanner();

        // Phase 3.1 fix: auto-poll the backend every 15 minutes so a
        // browser tab left open for days actually reflects the daily 09:00
        // cron output instead of freezing on whatever data was current
        // when the tab was first loaded. We re-pull metadata + the
        // currently-selected token's chart silently in the background.
        // The 15-min cadence is well under the 24h refresh interval and
        // far cheaper than full-page reload, but the user can still hit
        // the Refresh button or Cmd+Shift+R for an immediate update.
        if (!window._autoPollTimer) {
            window._autoPollTimer = setInterval(async () => {
                // Phase 3.7 (final architect P1-2): skip this tick if the
                // user is mid-click on the Refresh button. Otherwise the
                // auto-poll and onRefreshClick can both call
                // onTokenChange() concurrently → the chart redraws twice
                // and the indicator panels flicker. The next tick (15 min
                // later) will pick up whatever the manual refresh wrote.
                const refreshBtn = document.getElementById("refresh-btn");
                if (refreshBtn && refreshBtn.disabled) {
                    return;
                }
                try {
                    await loadSystemStatus();
                    await loadTokens();
                    await loadRankings();
                    if (typeof currentToken !== "undefined" && currentToken) {
                        await onTokenChange();
                    }
                    // P0-5 (UX audit): RobustnessPanel was only rendered once
                    // in init() — a tab left open for days would show stale
                    // backtest stats forever. Re-render on each poll.
                    if (typeof RobustnessPanel !== "undefined") {
                        RobustnessPanel.renderSummary(currentAssetClass);
                    }
                } catch (e) {
                    console.warn("[app] auto-poll failed:", e);
                }
            }, 15 * 60 * 1000);
        }
    }

    async function renderTierBBanner() {
        const el = document.getElementById("tier-b-banner");
        if (!el) return;
        // Phase 3 Module 6: replace the negative-Sharpe banner with a neutral
        // "linear-weighted research preview" message. Per user direction we
        // do NOT expose Sharpe inversion / reversed-direction numbers in the
        // user-facing banner. The underlying API endpoints
        // (/api/scoring/tier_b, /api/scoring/calibrated) still return the
        // full audit payload for internal researchers — we just don't surface
        // it as a headline number on the dashboard.
        el.textContent = "Linear-weighted composite · research preview";
        el.className = "tier-b-banner tier-b-fallback";
        el.title = "Overall score is a linear weighted blend of 6 sleeves "
                 + "(Trend 0.40, Reversal 0.25, Breadth 0.15, Risk 0.10, "
                 + "TS Trend 2y 0.05, TS Reversal 2y 0.05). Weights are "
                 + "theory priors, not learned from data. Research preview "
                 + "— not investment advice.";
        el.hidden = false;
    }

    // R8-3A: theme toggle — flip html[data-theme], persist to localStorage,
    // re-tint LightweightCharts and re-render SVG widgets without recreating
    // anything (preserves zoom + scroll state). The boot-time inline <script>
    // in index.html <head> has already resolved the initial theme before
    // stylesheet load to avoid a flash-of-wrong-theme.
    function wireThemeToggle() {
        const btn = document.getElementById("theme-toggle");
        if (!btn) return;
        btn.addEventListener("click", () => {
            const cur = document.documentElement.dataset.theme || "dark";
            const next = cur === "dark" ? "light" : "dark";
            document.documentElement.dataset.theme = next;
            try { localStorage.setItem("iosg-theme", next); } catch (e) {}
            // K-line + indicator panels: re-apply layout/grid/series colours.
            if (candleCtx && typeof CandleChart.retint === "function") {
                try { CandleChart.retint(candleCtx); } catch (e) {}
            }
            if (typeof IndicatorPanels !== "undefined" && IndicatorPanels.retintAll) {
                try { IndicatorPanels.retintAll(indicatorCharts); } catch (e) {}
            }
            // SVG widgets: re-render with the current palette.
            if (typeof ScoreGauge !== "undefined" && ScoreGauge.retintAll) {
                try { ScoreGauge.retintAll(); } catch (e) {}
            }
            // Sparklines: reload rankings so the new accent colours stick.
            try { loadRankings(); } catch (e) {}
        });
        // OS prefers-color-scheme is no longer honored (2026-05-15 user
        // directive: default theme = dark always; only the manual toggle
        // switches it). Listener removed so an OS dark-mode flip doesn't
        // override the user's choice.
    }

    // R8-1D: tab strip — switch asset_class, refresh tokenCatalog + rankings,
    // pick the per-class default token. Persist to URL hash.
    function wireAssetClassTabs() {
        const tabs = document.querySelectorAll(".sidebar-tabs .tab-btn");
        // Reflect initial state from currentAssetClass (set in init from hash).
        tabs.forEach(b => {
            b.classList.toggle("active", b.getAttribute("data-tab") === currentAssetClass);
        });
        tabs.forEach(btn => {
            btn.addEventListener("click", async () => {
                const target = btn.getAttribute("data-tab");
                if (target === currentAssetClass) return;
                currentAssetClass = target;
                tabs.forEach(b => b.classList.toggle("active", b === btn));
                // UX-audit final: preserve any token= in the hash by going
                // through the merged updater instead of overwriting the
                // whole fragment.
                _updateHash({ tab: target, token: null });
                await loadTokens();
                await loadRankings();
                const preferred = target === "us-stock" ? "CRCL" : "bitcoin";
                const fallback = tokenCatalog.find(t => t.has_ohlcv);
                const pick = tokenCatalog.find(t => t.id === preferred && t.has_ohlcv) || fallback;
                if (pick) selectToken(pick.id);
                // R8-2B: refresh robustness for new asset class.
                if (typeof RobustnessPanel !== "undefined") {
                    RobustnessPanel.renderSummary(target);
                }
            });
        });
    }

    // R6-7: enable the bottom-drawer behavior only on narrow viewports
    // (CSS already parks the sidebar; this wires the toggle handle and
    // tracks viewport changes so the handle hides on tablet/desktop).
    function wireMobileDrawer() {
        const handle = document.getElementById("drawer-handle");
        const sidebar = document.getElementById("sidebar");
        if (!handle || !sidebar) return;
        const mq = window.matchMedia("(max-width: 768px)");
        const sync = () => {
            handle.hidden = !mq.matches;
            if (!mq.matches) sidebar.classList.remove("expanded");
        };
        sync();
        if (mq.addEventListener) mq.addEventListener("change", sync);
        else if (mq.addListener) mq.addListener(sync);
        handle.addEventListener("click", () => {
            const open = sidebar.classList.toggle("expanded");
            handle.setAttribute("aria-expanded", String(open));
            const lbl = handle.querySelector(".drawer-label");
            if (lbl) lbl.textContent = open ? "Top 20 ▾" : "Top 20 ▴";
        });
    }

    async function loadTokens() {
        // R8-1D: scope to the active asset class so the combobox / rank
        // list only show what's relevant to the user's current tab.
        const data = await API.listTokens(currentAssetClass);
        tokenCatalog = (data.tokens || []).filter(t => t.has_ohlcv);
        // Phase 3.5: also keep a full cross-asset copy for refresh
        // progress labels (see _formatProgressToken).
        try {
            const dataAll = await API.listTokens("");
            tokenCatalogAll = (dataAll.tokens || []);
        } catch (e) {
            // non-fatal — fall back to using the scoped catalog
            tokenCatalogAll = tokenCatalog.slice();
        }
    }

    function _formatLabel(t) {
        const sym = (t.symbol || "").toUpperCase();
        return sym ? `${sym}  ·  ${t.name || t.id}` : (t.name || t.id);
    }

    function wireCombobox() {
        const input = document.getElementById("token-search");
        const dropdown = document.getElementById("token-dropdown");

        if (tokenCatalog.length === 0) {
            input.placeholder = "(no tokens loaded — POST /api/system/refresh)";
        }

        const showDropdown = (filterText) => {
            const q = (filterText || "").trim().toLowerCase();
            const matches = tokenCatalog.filter(t => {
                if (!q) return true;
                return (t.id && t.id.toLowerCase().includes(q)) ||
                       (t.symbol && t.symbol.toLowerCase().includes(q)) ||
                       (t.name && t.name.toLowerCase().includes(q));
            }).slice(0, 50);
            dropdownMatches = matches;
            dropdownActiveIdx = matches.length > 0 ? 0 : -1;
            renderDropdown(matches);
            dropdown.hidden = false;
        };

        const renderDropdown = (matches) => {
            dropdown.innerHTML = "";
            if (matches.length === 0) {
                const li = document.createElement("li");
                li.className = "empty";
                li.textContent = "No matches";
                dropdown.appendChild(li);
                return;
            }
            matches.forEach((t, i) => {
                const li = document.createElement("li");
                if (i === dropdownActiveIdx) li.classList.add("active");
                // R6-17: dim inactive (dropped-from-Top-200) tokens so the
                // user knows they're queryable for historical context but
                // are no longer in the daily-update set.
                if (t.active === false) {
                    li.classList.add("inactive");
                    li.title = "Inactive: no longer in CoinGecko Top-200; historical OHLCV preserved.";
                }
                const sym = document.createElement("span");
                sym.className = "opt-sym";
                sym.textContent = (t.symbol || "").toUpperCase() || "—";
                const name = document.createElement("span");
                name.className = "opt-name";
                name.textContent = t.name || t.id;
                const idel = document.createElement("span");
                idel.className = "opt-id";
                idel.textContent = t.id;
                li.appendChild(sym);
                li.appendChild(name);
                li.appendChild(idel);
                li.addEventListener("mousedown", (ev) => {
                    // mousedown fires before blur so we can update before the
                    // input loses focus.
                    ev.preventDefault();
                    selectToken(t.id);
                    dropdown.hidden = true;
                });
                dropdown.appendChild(li);
            });
        };

        input.addEventListener("focus", () => showDropdown(input.value));
        input.addEventListener("input", () => showDropdown(input.value));
        input.addEventListener("blur", () => {
            // Defer to let mousedown on dropdown fire first.
            setTimeout(() => { dropdown.hidden = true; }, 120);
        });
        input.addEventListener("keydown", (e) => {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                if (dropdownMatches.length === 0) return;
                dropdownActiveIdx = Math.min(dropdownActiveIdx + 1, dropdownMatches.length - 1);
                renderDropdown(dropdownMatches);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (dropdownMatches.length === 0) return;
                dropdownActiveIdx = Math.max(dropdownActiveIdx - 1, 0);
                renderDropdown(dropdownMatches);
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (dropdownMatches.length === 0) return;
                const idx = dropdownActiveIdx >= 0 ? dropdownActiveIdx : 0;
                const t = dropdownMatches[idx];
                if (t) {
                    selectToken(t.id);
                    dropdown.hidden = true;
                    input.blur();
                }
            } else if (e.key === "Escape") {
                dropdown.hidden = true;
                input.blur();
            }
        });
    }

    function selectToken(id) {
        const t = tokenCatalog.find(x => x.id === id);
        if (t) {
            const input = document.getElementById("token-search");
            input.value = _formatLabel(t);
        } else if (typeof Toast !== "undefined") {
            // Phase 3 Module 8.4 (PM): explicit "not found" hint instead of
            // silent no-op when an unknown id reaches selectToken (e.g.
            // programmatic call from a stale link).
            Toast.show(
                `Token "${id}" not in catalog — try BTC / ETH / SOL / CRCL.`,
                { kind: "warn", duration: 5000 }
            );
            return;
        }
        currentToken = id;
        // UX-audit final: write token id into URL hash so a quant researcher
        // can copy the URL and paste it to a colleague — they land on the
        // same token. Tab is preserved via the existing #tab= fragment.
        _updateHash({ token: id });
        onTokenChange();
        // R7-7: re-flag the .selected row in the rank list without doing a
        // full reload — surgical class toggle.
        _refreshRankSelection();
    }

    // URL hash helpers — store both #tab=<class> and #token=<id> in a single
    // fragment, e.g. "#tab=crypto&token=bitcoin". Backwards-compatible with
    // the existing "#tab=us-stock" parser in init().
    function _parseHash() {
        const out = {};
        const raw = (location.hash || "").replace(/^#/, "");
        for (const part of raw.split("&")) {
            const m = part.match(/^([a-z_]+)=([^&]+)$/i);
            if (m) out[m[1]] = decodeURIComponent(m[2]);
        }
        return out;
    }
    function _updateHash(patch) {
        const merged = Object.assign(_parseHash(), patch || {});
        const next = Object.keys(merged)
            .filter(k => merged[k] !== "" && merged[k] != null)
            .map(k => `${k}=${encodeURIComponent(merged[k])}`)
            .join("&");
        const newHash = next ? `#${next}` : "";
        if (location.hash !== newHash) {
            // Use replaceState so back-button history doesn't fill up.
            history.replaceState(null, "", location.pathname + location.search + newHash);
        }
    }

    function _refreshRankSelection() {
        document.querySelectorAll(".rank-list li").forEach(li => {
            const cid = li.getAttribute("data-cg-id");
            if (cid && cid === currentToken) {
                li.classList.add("selected");
                li.setAttribute("aria-current", "true");
            } else {
                li.classList.remove("selected");
                li.removeAttribute("aria-current");
            }
        });
    }

    async function loadRankings() {
        const mode = document.getElementById("rank-mode").value;
        // R8-1D: scope rankings to the active asset class.
        const data = await API.getRankings(mode, 20, currentAssetClass);
        // R7-6: topbar close-only chip — single source of truth is the
        // universe-wide aggregate from /api/rankings (was previously sourced
        // from last_run_summary.fallback in loadSystemStatus, which diverged
        // by ~3 because that field only counts today's daily-update set).
        const fbEl = document.getElementById("fallback-stat");
        if (fbEl) {
            const total = data.universe_close_only;
            if (total != null && total > 0) {
                // Build the chip text + a visible `?` info-mark so users
                // see this is hoverable. The chip itself also carries
                // title= for legacy hover.
                const tipText = `DEFINITION: ${total} tokens in today's crypto universe carry CoinGecko Tier-4 close-only data — no real OHLCV from any of our 8 spot exchanges (Binance / OKX / Bybit / Gate.io / Coinbase / Kraken / KuCoin / Bitstamp). FORMAT OF THE FALLBACK: only daily close price, with open = high = low = close synthetic, volume = 0. CONSEQUENCES: KDJ and Volume Spike signals are automatically NaN-suppressed for these tokens (the math requires real H/L/V). Reversal score reliability is reduced by ~30% for the affected universe slice. WHY THIS HAPPENS: the token has no spot trading pair on any of the 8 exchanges we integrate with — typically niche tokenized stocks, very long-tail meme coins, or recently listed tokens that haven't reached major exchanges. PLAN TARGET ≈ 5 of 200, ACTUAL ${total} — universe currently has more long-tail tokens than expected.`;
                fbEl.innerHTML = `${total} close-only <span class="info-mark" title="${tipText.replace(/"/g, '&quot;')}">?</span>`;
                fbEl.title = tipText;
                fbEl.hidden = false;
                if (typeof ExplainerModal !== "undefined" && ExplainerModal.wire) {
                    ExplainerModal.wire();
                }
            } else {
                fbEl.hidden = true;
            }
        }
        const list = document.getElementById("rank-list");
        list.innerHTML = "";
        const spark_targets = {};
        data.scores.forEach((row, idx) => {
            const li = document.createElement("li");
            li.setAttribute("data-cg-id", row.cg_id);    // R7-7: lookup hook
            const rank = idx + 1;
            if (rank <= 3) li.classList.add("top-rank");
            // R7-7: highlight the currently-selected token so the user can
            // see at a glance "this is the row I'm looking at right now."
            if (row.cg_id === currentToken) {
                li.classList.add("selected");
                li.setAttribute("aria-current", "true");
            }
            li.title = `${row.symbol || row.cg_id} — ${row.name || row.cg_id}`;

            const badge = document.createElement("span");
            badge.className = "rank-badge";
            badge.textContent = "#" + rank;

            const text = document.createElement("span");
            text.className = "rank-text";
            const sym = document.createElement("span");
            sym.className = "rank-symbol";
            sym.textContent = (row.symbol || row.cg_id || "").toUpperCase();
            const name = document.createElement("span");
            name.className = "rank-name";
            name.textContent = row.name || row.cg_id;
            text.appendChild(sym);
            text.appendChild(name);

            // P2-3: sparkline placeholder; populated below in a single batch call.
            const sparkSpan = document.createElement("span");
            sparkSpan.className = "rank-spark";
            spark_targets[row.cg_id] = sparkSpan;

            const score = document.createElement("span");
            // UX-audit final: when mode=overall pull the composite score
            // instead of falling through to trend by default.
            let v;
            if (mode === "overall")        v = row.overall_score;
            else if (mode === "reversal")  v = row.reversal_score;
            else                            v = row.trend_score;
            score.className = "rank-score " + scoreTierClass(v);
            score.textContent = v == null ? "--" : v.toFixed(1);

            li.appendChild(badge);
            li.appendChild(text);
            li.appendChild(sparkSpan);
            // R6-4: warn the analyst when KDJ/volume signals are NaN-suppressed
            // for this token. The dot is yellow (caution), tooltip on hover.
            if (row.close_only_data) {
                const cap = document.createElement("span");
                cap.className = "rank-cap";
                cap.textContent = "⚠";
                cap.title = CLOSE_ONLY_TIP;
                cap.setAttribute("aria-label", "Close-only data warning");
                li.appendChild(cap);
            }
            li.appendChild(score);
            li.addEventListener("click", () => {
                selectToken(row.cg_id);
            });
            list.appendChild(li);
        });
        if (typeof ExplainerModal !== "undefined" && ExplainerModal.wire) {
            ExplainerModal.wire();
        }

        // P2-3: single batched fetch for all visible sparklines.
        const ids = Object.keys(spark_targets);
        if (ids.length > 0) {
            const sp = await API.getSparklines(ids, 30).catch(() => null);
            if (sp && sp.sparklines) {
                for (const id of ids) {
                    const values = sp.sparklines[id];
                    if (values) Sparkline.render(spark_targets[id], values);
                }
            }
        }
    }

    function scoreTierClass(v) {
        if (v == null) return "score-mid";
        if (v >= 66) return "";          // default green
        if (v >= 33) return "score-mid"; // yellow
        return "score-low";              // red
    }

    function scoreLargeClass(v) {
        if (v == null) return "score-neutral";
        if (v >= 66) return "score-strong";
        if (v >= 33) return "score-neutral";
        return "score-weak";
    }

    // Phase 3 Module 2: human-friendly "Updated X ago" from an ISO timestamp.
    // Uses the BROWSER's local clock (no external NTP call) — system time
    // is already NTP-synced via the OS. Returns e.g. "2 hours ago", "3 days
    // ago", "just now". Returns "never" for missing inputs.
    function _relativeTime(isoStr) {
        if (!isoStr) return "never";
        const t = new Date(isoStr);
        if (isNaN(t.getTime())) return isoStr;
        const diffSec = Math.max(0, Math.floor((Date.now() - t.getTime()) / 1000));
        if (diffSec < 60)      return "just now";
        if (diffSec < 3600)    return `${Math.floor(diffSec / 60)} min ago`;
        if (diffSec < 86400)   return `${Math.floor(diffSec / 3600)} hours ago`;
        if (diffSec < 86400*2) return "1 day ago";
        return `${Math.floor(diffSec / 86400)} days ago`;
    }

    async function loadSystemStatus() {
        const data = await API.getSystemStatus();
        const last = data.last_update || {};
        const ts = last.last_ohlcv_update || null;
        const relTopbar = _relativeTime(ts);
        const topbarEl = document.getElementById("last-update");
        if (topbarEl) {
            topbarEl.textContent = `Updated ${relTopbar}`;
            topbarEl.title = ts ? `Source timestamp: ${ts}` : "No update timestamp available";
        }
        // Phase 3 Module 2: footer also surfaces the freshness + version.
        const footerRefresh = document.getElementById("footer-last-refresh");
        if (footerRefresh) {
            footerRefresh.textContent = `Last data refresh: ${relTopbar}`;
            footerRefresh.title = ts ? `Source: ${ts}` : "";
        }
        const footerVersion = document.getElementById("footer-version");
        if (footerVersion) {
            footerVersion.textContent = data.version ? `v${data.version}` : "v3.0.0";
        }
        // R6-4: surface the close-only fallback count so operators see when
        // the universe-wide data fidelity drifts. last_run_summary.fallback
        // is written by fetcher.run_daily_update / run_full_initial_load.
        // R7-6: the topbar close-only chip is now populated by loadRankings()
        // from the universe-wide `universe_close_only` aggregate (single
        // source of truth), not the per-run `last_run_summary.fallback`
        // count — those two diverged by 3 (32 vs 35) because `fallback` only
        // counts tokens in today's daily-update set, missing inactive
        // historical tokens that still scan close-only. Don't touch the
        // #fallback-stat element here; let loadRankings own it.
        // R6-9: surface exchange_health from last_update.json. Show a red
        // chip listing any unavailable exchanges (zero markets returned at
        // boot) so operators see the data-redundancy degradation.
        const eh = last.exchange_health || {};
        const ehEl = document.getElementById("exchange-health");
        if (ehEl) {
            const down = Object.keys(eh).filter(k => eh[k] && eh[k].available === false);
            if (down.length > 0) {
                ehEl.textContent = `⚠ ${down.join(" / ")} unavailable`;
                ehEl.title = `${down.length} exchange(s) returned 0 markets at boot — likely geo-blocked from this host or API-changed. The waterfall PLAN sec 3.1 expects Binance→OKX→Bybit→Gate.io; effective chain is reduced to the remaining providers + CoinGecko close-only.`;
                ehEl.hidden = false;
            } else {
                ehEl.hidden = true;
            }
        }
    }

    async function onTokenChange() {
        const id = currentToken;
        if (!id) return;

        // P0-J: synchronously reset the close-only badge BEFORE any await.
        // Previously the badge state was only updated AFTER `await API.getToken(id)`
        // resolved, so any rejection (network blip, transient 5xx, ad-blocker)
        // left the prior token's badge visible — a "sticky" data-quality
        // misrepresentation. Resetting up-front is the simplest fix that holds
        // even if downstream fetches throw. Chosen option (b) per Round-5 spec.
        const closeBadge = document.getElementById("badge-close-only");
        if (closeBadge) closeBadge.hidden = true;

        // --- Header info
        const token = await API.getToken(id);
        document.getElementById("token-name").textContent = token.name || id;
        if (token.last_close != null) {
            document.getElementById("token-price").textContent = `$${token.last_close.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
        } else {
            document.getElementById("token-price").textContent = "--";
        }
        // P0-C: render a "Close-only data" badge for CoinGecko-fallback tokens.
        // The badge is permanently in the DOM but hidden; we toggle visibility.
        if (closeBadge && token && token.close_only_data) {
            closeBadge.hidden = false;
        }

        // --- Score badges + detail
        // P1-F: /api/scores/{id} now returns 200 with null score fields for
        // close-only / short-history tokens (mirror of P0-I). Guard each
        // numeric read against null so the badges render "--" instead of
        // throwing TypeError on null.toFixed().
        const sc = await API.getScore(id).catch(() => null);
        const sObj = sc && sc.score;
        const tVal = sObj && sObj.trend_score;
        const rVal = sObj && sObj.reversal_score;
        document.getElementById("badge-trend").textContent =
            tVal == null ? "--" : tVal.toFixed(1);
        document.getElementById("badge-reversal").textContent =
            rVal == null ? "--" : rVal.toFixed(1);
        if (sObj && tVal != null && rVal != null) {
            renderScoreDetail(sObj);
        }

        // --- R8-1C: market info tiles (mcap rank / mcap / 24h vol / 30d vol / liquidity)
        await MarketPanel.render(id);

        // --- R8-1B.2 / Q14: per-token data coverage folding row
        await renderDataCoverage(id);

        // --- K-line chart
        await renderCandle(id);
        // --- All 12 indicator panels
        await renderAllIndicators(id);
    }

    async function renderCandle(id) {
        const container = document.getElementById("chart-candle");
        container.innerHTML = "";
        candleCtx = CandleChart.create(container);
        // Phase-2 item 11: pull the full extended history (2020-01-01 → today,
        // 2326 days) so users can see the 6-year backdrop including
        // COVID crash, FTX, halving regime shifts. Plan note (original):
        // "the default chart can keep showing the last 1-year K-line"
        // — superseded by 2026-05-15 user directive: show all history,
        // handled by fitContent()
        // calling setVisibleLogicalRange in wireTimeSync to zoom to ~1y,
        // user can scroll/pan to earlier years freely.
        const data = await API.getOhlc(id, 2326);
        CandleChart.setData(candleCtx, data.ohlcv || []);
        // User preference: default viewport shows ALL history (2020 → today
        // for old tokens, listing-day → today for younger ones). User can
        // pinch/scroll to zoom into a sub-range. fitContent() achieves this.
        candleCtx.chart.timeScale().fitContent();
        wireTimeSync(candleCtx.chart);
        // P1-D: wireTimeSync subscribes AFTER fitContent, so the initial
        // visible range (post-fit) is never broadcast to indicator
        // panels — the candle showed 365 days while indicators showed
        // ~75. Fan the post-fit logical range out once, here, so every
        // indicator chart starts on the same x-axis window. We invoke
        // it on the next animation frame to give Lightweight Charts a
        // tick to register indicator subscriptions.
        requestAnimationFrame(() => broadcastMasterRange());
    }

    function broadcastMasterRange() {
        if (!candleCtx) return;
        const range = candleCtx.chart.timeScale().getVisibleLogicalRange();
        if (!range) return;
        isSyncing = true;
        for (const chart of Object.values(indicatorCharts)) {
            try {
                chart.timeScale().setVisibleLogicalRange(range);
            } catch (e) { /* ignore per-chart sync errors */ }
        }
        isSyncing = false;
    }

    async function renderAllIndicators(id) {
        // Destroy prior charts to free up memory.
        for (const fam of Object.keys(indicatorCharts)) {
            try { indicatorCharts[fam].remove(); } catch (e) {}
            delete indicatorCharts[fam];
        }
        // Phase-2 item 11: pull full history so indicators align with the
        // 2020-2026 candle range. (was 365 — capped indicators to 1y).
        const data = await API.getIndicators(id, 2326);
        const series = data.series || {};
        for (const fam of FAMILIES) {
            const container = document.getElementById(`chart-${fam}`);
            if (!container) continue;
            container.innerHTML = "";
            const chart = IndicatorPanels.renderFamily(fam, container, series);
            if (chart) {
                indicatorCharts[fam] = chart;
            }
        }
        // P1-D: now that every indicator panel chart exists, broadcast the
        // master candle's post-fit logical range so every panel starts on
        // the same x-axis window. Without this, the candle shows 365 days
        // and each panel collapses to its own auto-fit (~75 days).
        requestAnimationFrame(() => broadcastMasterRange());
    }

    // P2-1: per-panel reload with caller-supplied params (no debounce here —
    // the debounce wrapper sits in wireParamControls). Used by parameter
    // controls in each indicator panel header.
    async function reloadPanel(fam, params) {
        const id = currentToken;
        if (!id) return;
        const container = document.getElementById(`chart-${fam}`);
        if (!container) return;
        const data = await API.getFamily(id, fam, 2326, params).catch(() => null);
        if (!data || !data.series) return;
        if (indicatorCharts[fam]) {
            try { indicatorCharts[fam].remove(); } catch (e) {}
            delete indicatorCharts[fam];
        }
        container.innerHTML = "";
        const chart = IndicatorPanels.renderFamily(fam, container, data.series);
        if (chart) {
            indicatorCharts[fam] = chart;
            // Sync the new panel to the candle's current visible range so
            // the freshly recomputed panel doesn't pop to its own auto-fit.
            if (candleCtx) {
                const range = candleCtx.chart.timeScale().getVisibleLogicalRange();
                if (range) {
                    try { chart.timeScale().setVisibleLogicalRange(range); } catch (e) {}
                }
            }
        }
    }

    // P2-1: wire <input data-param=*> + reset buttons in every .indicator-panel
    // header. 300ms debounce per panel matches PLAN §7.3.
    // R7-1: also rewrite the .panel-title span from `data-title-template` so the
    // header text reflects the live parameter state instead of being a static
    // literal that lies after the user changes a value.
    const _panelDefaults = {};   // fam -> {paramKey: defaultValue}
    function _renderPanelTitle(panel) {
        const tpl = panel.getAttribute("data-title-template");
        if (!tpl) return;
        const titleEl = panel.querySelector(".panel-title");
        if (!titleEl) return;
        const inputs = panel.querySelectorAll("input[data-param]");
        let next = tpl;
        inputs.forEach(inp => {
            const key = inp.getAttribute("data-param");
            const v = (inp.value === "" || inp.value == null) ? (inp.defaultValue || "") : inp.value;
            next = next.split("{" + key + "}").join(v);
        });
        titleEl.textContent = next;
    }
    // R8-3D · param-label tooltips. Plan Part 3.3 lists 7 param-name keys
    // (period / fast / slow / signal / N / M1 / M2 / std / window) and a one-
    // line tooltip each. Injected via JS so we don't have to add title=
    // attributes on every duplicate <label> instance (~15 in the HTML).
    const PARAM_TOOLTIPS = {
        period:   "Lookback window in bars (days).",
        fast:     "Number of bars in the faster moving average. Smaller fast = more sensitive but more whipsaws.",
        slow:     "Number of bars in the slower moving average. Larger slow = smoother trend reference, slower turns.",
        signal:   "Smoothing window applied to the MACD line to compute the signal line (default 9).",
        N:        "KDJ stochastic window — number of bars used to compute the raw %K.",
        M1:       "KDJ: K-line smoothing factor (default 3).",
        M2:       "KDJ: D-line smoothing factor (default 3).",
        num_std:  "Number of standard deviations defining the Bollinger band width (default 2σ).",
        ma_window:"Number of bars in the volume moving-average baseline used by Volume Spike.",
    };

    function wireParamControls() {
        const panels = document.querySelectorAll(".indicator-panel[data-family]");
        const timers = {};
        panels.forEach(panel => {
            const fam = panel.getAttribute("data-family");
            const inputs = panel.querySelectorAll("input[data-param]");
            // R8-3D: wire native title= on every <label> wrapping a param input.
            inputs.forEach(inp => {
                const key = inp.getAttribute("data-param");
                const tip = PARAM_TOOLTIPS[key];
                if (tip && inp.parentElement && inp.parentElement.tagName === "LABEL") {
                    inp.parentElement.title = tip;
                }
            });
            const defaults = {};
            inputs.forEach(inp => { defaults[inp.getAttribute("data-param")] = inp.value; });
            _panelDefaults[fam] = defaults;
            // R7-1: render the title once from defaults so any rounding /
            // formatting matches the template (e.g. "Bollinger (20, 2σ)").
            _renderPanelTitle(panel);
            const trigger = () => {
                // R7-1: title responds immediately to the user's keystroke
                // (no debounce on the cheap DOM rewrite); only the network
                // call goes through the 300 ms debounce.
                _renderPanelTitle(panel);
                if (timers[fam]) clearTimeout(timers[fam]);
                timers[fam] = setTimeout(() => {
                    const params = {};
                    inputs.forEach(inp => {
                        const key = inp.getAttribute("data-param");
                        const v = inp.value;
                        if (v !== "" && v != null) params[key] = v;
                    });
                    reloadPanel(fam, params);
                }, 300);
            };
            inputs.forEach(inp => {
                inp.addEventListener("input", trigger);
                inp.addEventListener("change", trigger);
            });
            const resetBtn = panel.querySelector(".param-reset");
            if (resetBtn) {
                resetBtn.addEventListener("click", () => {
                    inputs.forEach(inp => {
                        const key = inp.getAttribute("data-param");
                        inp.value = defaults[key];
                    });
                    trigger();
                });
            }
        });
    }

    function wireTimeSync(masterChart) {
        masterChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
            if (isSyncing || !range) return;
            isSyncing = true;
            for (const chart of Object.values(indicatorCharts)) {
                try {
                    chart.timeScale().setVisibleLogicalRange(range);
                } catch (e) { /* ignore per-chart sync errors */ }
            }
            isSyncing = false;
        });
    }

    // R8-1B.2 / Q14: render the Data Coverage folding row.
    // Shows "Real OHLC from YYYY-MM-DD · close-only from ... to ..." in the
    // summary, with a tier_breakdown table inside the <details> body.
    async function renderDataCoverage(cgId) {
        const section = document.getElementById("data-coverage");
        const headlineEl = document.getElementById("data-coverage-headline");
        const bodyEl = document.getElementById("data-coverage-body");
        if (!section || !headlineEl || !bodyEl) return;
        let resp;
        try { resp = await API.getDataCoverage(cgId); }
        catch (e) {
            section.hidden = true;
            return;
        }
        const cov = (resp && resp.coverage) || resp;
        if (!cov || typeof cov !== "object") {
            section.hidden = true;
            return;
        }
        section.hidden = false;
        const earliest = cov.earliest_date || "—";
        const latest = cov.latest_date || "—";
        const real = cov.real_ohlc_from;
        const closeWindows = cov.close_only_windows || [];
        let head = `${earliest} → ${latest}`;
        if (real && earliest && real !== earliest) {
            head += ` · real OHLC from ${real}`;
        }
        if (closeWindows.length) {
            head += ` · ${closeWindows.length} close-only window(s)`;
        }
        headlineEl.textContent = head;

        const tiers = cov.tier_breakdown || [];
        if (!tiers.length) {
            bodyEl.innerHTML = `<p class="muted">No per-segment breakdown available.</p>`;
            return;
        }
        let html = `<table class="data-coverage-table"><thead><tr>
            <th>From</th><th>To</th><th>Source</th><th>Tier</th><th>Rows</th>
        </tr></thead><tbody>`;
        for (const seg of tiers) {
            html += `<tr>
                <td>${seg.from || "—"}</td>
                <td>${seg.to || "—"}</td>
                <td>${seg.source || "—"}</td>
                <td>${seg.tier == null ? "—" : seg.tier}</td>
                <td class="num">${seg.rows == null ? "—" : seg.rows}</td>
            </tr>`;
        }
        html += `</tbody></table>`;
        bodyEl.innerHTML = html;
    }

    function renderScoreDetail(score) {
        // P2-2 + R6-2: SVG dial paired with the HTML .score-large hero number.
        // R8-2A: also render Overall hero card (overall_score + 6-row sleeve breakdown).
        // R8-2C: rank chips ("Rank N / M") on all three cards.
        ScoreGauge.render(document.getElementById("trend-gauge"), score.trend_score);
        ScoreGauge.render(document.getElementById("reversal-gauge"), score.reversal_score);
        ScoreGauge.render(document.getElementById("overall-gauge"), score.overall_score);

        const tEl = document.getElementById("trend-value");
        const rEl = document.getElementById("reversal-value");
        const oEl = document.getElementById("overall-value");
        if (tEl) {
            tEl.textContent = score.trend_score == null ? "--" : score.trend_score.toFixed(1);
            tEl.className = "score-large " + scoreLargeClass(score.trend_score);
        }
        if (rEl) {
            rEl.textContent = score.reversal_score == null ? "--" : score.reversal_score.toFixed(1);
            rEl.className = "score-large " + scoreLargeClass(score.reversal_score);
        }
        if (oEl) {
            oEl.textContent = score.overall_score == null ? "--" : score.overall_score.toFixed(1);
            oEl.className = "score-large score-xl " + scoreLargeClass(score.overall_score);
        }

        // R8-2C: rank chips
        const u = score.universe_size;
        const _rank = (v) => (v == null || u == null) ? "Rank — / —" : `Rank ${v} / ${u}`;
        const ovRankEl = document.getElementById("overall-rank");
        const trRankEl = document.getElementById("trend-rank");
        const rvRankEl = document.getElementById("reversal-rank");
        if (ovRankEl) ovRankEl.textContent = _rank(score.rank_in_universe_overall);
        if (trRankEl) trRankEl.textContent = _rank(score.rank_in_universe_trend);
        if (rvRankEl) rvRankEl.textContent = _rank(score.rank_in_universe_reversal);

        // R8-2A: blurb (4-quadrant interpretation)
        const blurbEl = document.getElementById("overall-blurb");
        if (blurbEl) blurbEl.textContent = _scoreBlurb(score.trend_score, score.reversal_score);

        // Percentile context lines (existing trend/reversal cards)
        const tp = `Cross-sectional: Top ${(100 - score.trend_cs_percentile).toFixed(0)}%` +
            (score.trend_ts_2y_percentile != null ? ` / 2y: Top ${(100 - score.trend_ts_2y_percentile).toFixed(0)}%` : "") +
            (score.trend_ts_3y_percentile != null ? ` / 3y: Top ${(100 - score.trend_ts_3y_percentile).toFixed(0)}%` : "");
        document.getElementById("trend-percentiles").textContent = tp;

        const rp = `Cross-sectional: Top ${(100 - score.reversal_cs_percentile).toFixed(0)}%` +
            (score.reversal_ts_2y_percentile != null ? ` / 2y: Top ${(100 - score.reversal_ts_2y_percentile).toFixed(0)}%` : "") +
            (score.reversal_ts_3y_percentile != null ? ` / 3y: Top ${(100 - score.reversal_ts_3y_percentile).toFixed(0)}%` : "");
        document.getElementById("reversal-percentiles").textContent = rp;

        // R8-2A: Overall card percentile context
        const op = score.overall_cs_percentile != null
            ? `Overall Top ${(100 - score.overall_cs_percentile).toFixed(0)}% of universe`
            : "";
        const ovpEl = document.getElementById("overall-percentiles");
        if (ovpEl) ovpEl.textContent = op;

        renderComponents("trend-components", score.trend_components || {});
        renderComponents("reversal-components", score.reversal_components || {});
        // R8-2A: 6-sleeve breakdown for Overall card
        renderOverallSleeves(score.overall_components || []);
    }

    // R8-2A: 4-quadrant interpretation phrase. Trend ≥ 66 = strong; ≤ 33 = weak.
    function _scoreBlurb(t, r) {
        if (t == null || r == null) return "—";
        const strongT = t >= 66, weakT = t < 33;
        const strongR = r >= 66, weakR = r < 33;
        if (strongT && weakR) return "Strong bull setup — momentum without exhaustion.";
        if (weakT && strongR) return "Oversold rebound candidate — watch for reversal trigger.";
        if (strongT && strongR) return "Conflicted — bullish trend AND oversold reversal.";
        if (weakT && weakR) return "Weak across the board — no edge either direction.";
        return "Mixed signals — wait for confirmation.";
    }

    // R8-2A: render the 6-row sleeve breakdown inside .components-overall
    function renderOverallSleeves(rows) {
        const ul = document.getElementById("overall-components");
        if (!ul) return;
        ul.innerHTML = "";
        rows.forEach(row => {
            const li = document.createElement("li");
            // R8-3D: attach sleeve tooltip to the whole <li> so hover anywhere
            // on the row reveals what the sleeve measures.
            const sleeveKey = row.sleeve || row.key;
            const tt = COMPONENT_TOOLTIPS[row.key]
                    || COMPONENT_TOOLTIPS[sleeveKey]
                    || COMPONENT_TOOLTIPS[(row.label || "").toLowerCase()];
            if (tt) li.title = tt;
            const label = document.createElement("span");
            label.className = "sleeve-label";
            label.textContent = row.label;
            const val = document.createElement("span");
            val.className = "sleeve-value";
            val.textContent = row.value == null ? "--" : row.value.toFixed(1);
            const wt = document.createElement("span");
            wt.className = "sleeve-weight";
            wt.textContent = `× ${(row.weight * 100).toFixed(0)}%`;
            const contrib = document.createElement("span");
            contrib.className = "sleeve-contrib";
            contrib.textContent = (row.contribution == null) ? "" : `= ${row.contribution.toFixed(1)}`;
            // UX-audit final review: 6 sleeve rows must each have a `?` that
            // opens the explainer modal. Previously only 3 (overall/trend/
            // reversal) had explainers; analyst writing morning note hit a
            // dead-end on Breadth/Risk/TS_Trend_2y/TS_Rev_2y. Backend
            // explainers.py now ships all 7 entries.
            if (sleeveKey) {
                const info = document.createElement("span");
                info.className = "info-mark";
                info.setAttribute("data-explainer", sleeveKey);
                info.setAttribute("aria-label", `Explain ${row.label}`);
                if (tt) info.title = tt;
                info.textContent = "?";
                li.appendChild(label);
                li.appendChild(info);
            } else {
                li.appendChild(label);
            }
            li.appendChild(val);
            li.appendChild(wt);
            li.appendChild(contrib);
            ul.appendChild(li);
        });
        // Re-wire the newly inserted .info-mark[data-explainer] nodes.
        if (typeof ExplainerModal !== "undefined" && ExplainerModal.wire) {
            ExplainerModal.wire();
        }
    }

    // R8-3C: human-friendly English labels for the 9 trend + 7 reversal
    // signal identifiers. Single source of truth — unmapped keys fall back to
    // the raw backend identifier so newly added signals are still visible.
    // Note: ma50_dev (trend) and ma50_dev_z_40 (reversal) were both labelled
    // identically ("MA50 Deviation") in the Chinese version; distinguished in
    // English (Deviation vs Deviation Z) to remove the collision.
    const COMPONENT_LABELS = {
        // 9 trend signals
        mom_ret_10d: "Momentum (10d)",
        mom_ret_20d: "Momentum (20d)",
        macd_hist_12_26_9: "MACD Histogram",
        macd_hist_slope5_12_26_9: "MACD Histogram Slope (5d)",
        sma_cross_strength_signed_5_20: "SMA Cross Strength (5/20)",
        ema_cross_strength_signed_5_20: "EMA Cross Strength (5/20)",
        ma50_slope_20d: "MA50 Slope (20d)",
        ma50_dev: "MA50 Deviation",
        bb_pctb_20: "Bollinger %B (20)",
        // 7 reversal signals
        rsi_dist_os_14: "RSI Oversold Distance (14)",
        rsi_turn_event_14: "RSI Turn Event (14)",
        kdj_os_distance: "KDJ Oversold Distance",
        bb_z_20: "Bollinger Z-Score (inverted, 20)",
        mr_z_40_skip16: "Mean Reversion Z (40, skip 16)",
        ma50_dev_z_40: "MA50 Deviation Z (40)",
        mom_ret_5d: "Negative Momentum (5d)",
    };

    // R8-3D: signal-level tooltips for Score Breakdown rows. Native title=
    // attribute drives the hover popup; popover.js could swap these in
    // later for a styled bubble if desired.
    const COMPONENT_TOOLTIPS = {
        mom_ret_10d: "10-day log return, ranked cross-sectionally to 0–100 within today's universe. Higher = stronger recent uptrend vs peers.",
        mom_ret_20d: "20-day log return, cross-sectionally ranked. Confirms whether the 10d move is a continuation or a one-off pop.",
        macd_hist_12_26_9: "MACD(12,26,9) histogram value, cross-sectionally ranked. Positive and growing = bullish acceleration.",
        macd_hist_slope5_12_26_9: "Slope of the MACD histogram over the last 5 bars. Captures acceleration of acceleration — turns sign before the histogram itself does.",
        sma_cross_strength_signed_5_20: "Signed normalized gap between fast and slow SMA. Positive = fast above slow (golden-cross regime); magnitude scales the rank.",
        ema_cross_strength_signed_5_20: "Same as SMA cross but with EMAs — reacts faster to recent prices.",
        ma50_slope_20d: "Slope of the 50-day moving average over the last 20 days. Positive = the medium-term trend is curving upward.",
        ma50_dev: "Percentage distance of price above its 50-day MA. Positive in uptrends; very high values can presage exhaustion.",
        bb_pctb_20: "Where price sits within its 20-day Bollinger band. 1.0 = upper band, 0.5 = mean, 0.0 = lower band.",
        rsi_dist_os_14: "How far RSI is below the 30 oversold threshold. Larger = more deeply oversold = stronger reversal-candidate.",
        rsi_turn_event_14: "Captures the moment RSI re-crosses 30 from below. Discrete bullish reversal trigger.",
        kdj_os_distance: "Stochastic K distance below 20. Larger = more oversold on a higher-volatility-aware scale than RSI.",
        bb_z_20: "Standardized %B with sign flipped so that 'near lower band' produces a high reversal score.",
        mr_z_40_skip16: "Z-score of price vs its trailing 40-day mean, skipping the most recent 16 days to avoid lookback contamination. Very negative = stretched below mean.",
        ma50_dev_z_40: "Z-score of the MA50 deviation series over a 40-day window. Detects when '% above MA50' is itself stretched.",
        mom_ret_5d: "Inverted 5-day return. High values indicate recent weakness, which the reversal model treats as a setup for a snapback.",
        // 6 sleeves used by the Overall hero card
        trend: "DEFINITION: Trend sleeve. FORMULA: take the 9 atomic trend signals, percentile-rank each across today's active asset-class universe, equal-weight average them, then percentile-rank the blended value again as Trend_CS%. Signals are 10d/20d momentum, MACD histogram, MACD histogram slope, SMA cross strength, EMA cross strength, MA50 slope, MA50 deviation, and Bollinger %B. OVERALL WEIGHT: 40%. INTERPRETATION: high Trend means this token has stronger directional momentum and moving-average confirmation than peers.",
        reversal: "DEFINITION: Reversal sleeve. FORMULA: take the 7 atomic reversal signals, orient them so 'more oversold / more bounce setup' is higher, percentile-rank each across the universe, equal-weight average, then percentile-rank the blended value as Reversal_CS%. Signals are RSI oversold distance, RSI turn event, KDJ oversold distance, inverted Bollinger Z, mean-reversion Z, inverted MA50-deviation Z, and inverted 5d return. OVERALL WEIGHT: 25%. INTERPRETATION: high Reversal means stronger mean-reversion candidate, especially when Trend is low.",
        breadth: "DEFINITION: Signal Breadth sleeve. FORMULA: count how many of the 9 trend signals are positive for this token, divide by the number of non-NaN trend signals, then percentile-rank that percentage across the active universe. Example: 6 positive signals out of 9 = 66.7% raw breadth before cross-sectional ranking. OVERALL WEIGHT: 15%. INTERPRETATION: high Breadth means the trend score is supported by many independent signals rather than one noisy spike.",
        risk: "DEFINITION: Risk (low vol) sleeve. FORMULA: compute daily log-return volatility over the last 20 bars, annualize it with sqrt(365) for crypto (sqrt(252) for stocks), multiply by -1, then cross-sectionally percentile-rank so lower realized volatility receives a higher 0-100 score. OVERALL WEIGHT: 10%. INTERPRETATION: high Risk score does NOT mean high risk; it means lower recent volatility and cleaner position sizing. Low Risk score means the token is volatile relative to peers.",
        ts_trend_2y: "DEFINITION: Trend TS 2y sleeve. TS = time-series percentile, not cross-sectional percentile. FORMULA: rebuild this token's daily Trend score history over the last 2 years, then ask where today's Trend score sits inside that token's own historical distribution: percentile = % of past 2y days with Trend <= today's Trend. OVERALL WEIGHT: 5%. INTERPRETATION: high value means this token's current trend is unusually strong for itself, even if it is not top-ranked versus other tokens.",
        ts_reversal_2y: "DEFINITION: Reversal TS 2y sleeve. TS = time-series percentile. FORMULA: rebuild this token's daily Reversal score history over the last 2 years, then compute today's percentile within that token's own past values: percentile = % of past 2y days with Reversal <= today's Reversal. OVERALL WEIGHT: 5%. INTERPRETATION: high value means this token is unusually oversold / reversal-like compared with its own history. Useful for catching rare token-specific extremes that cross-sectional ranking can dilute.",
    };
    function renderComponents(elemId, comps) {
        const ul = document.getElementById(elemId);
        ul.innerHTML = "";
        for (const k of Object.keys(comps)) {
            const li = document.createElement("li");
            const name = document.createElement("span");
            name.textContent = COMPONENT_LABELS[k] || k;
            // R8-3D: substantive native tooltip per signal. Falls back to raw
            // key for unknown signals so devs can still see what's rendering.
            name.title = COMPONENT_TOOLTIPS[k] || k;
            const val = document.createElement("span");
            const v = comps[k];
            val.textContent = (v == null) ? "--" : (typeof v === "number" ? v.toFixed(4) : String(v));
            li.appendChild(name);
            li.appendChild(val);
            ul.appendChild(li);
        }
    }

    async function onRefreshClick() {
        // P1-H: poll /api/system/status until last_run_summary.finished_at
        // advances past the pre-refresh marker, then reload tokens/rankings.
        // Phase 3.1: also poll /api/system/refresh-progress to drive a real
        // progress bar inside the refresh button.
        const btn = document.getElementById("refresh-btn");
        const labelEl = document.getElementById("refresh-label");
        const barEl = document.getElementById("refresh-progress-bar");
        btn.disabled = true;
        btn.classList.remove("refresh-btn-timeout");
        if (labelEl) labelEl.textContent = "Starting…";
        if (barEl)   barEl.style.width = "0%";
        const preStatus = await API.getSystemStatus().catch(() => ({}));
        const preFinished = ((preStatus.last_update || {}).last_run_summary || {}).finished_at || null;
        let refreshResponse = null;
        try {
            refreshResponse = await API.postRefresh(false);
        } catch (e) {
            btn.disabled = false;
            if (labelEl) labelEl.textContent = "Refresh";
            if (barEl)   barEl.style.width = "0%";
            console.error(e);
            return;
        }
        // Phase 3.2 (architect P1): the server returns {status:"skipped"}
        // when another refresh (auto-cron / hourly self-heal / second click)
        // already owns the in-flight lock. Without this branch, the
        // finish-poller waits 10 min for finished_at to advance — which
        // it never will for the skipped caller — then times out. Better:
        // attach to the in-flight run via the progress poller and exit
        // cleanly when phase returns to "idle".
        const wasSkipped = refreshResponse
            && (refreshResponse.status === "skipped");
        if (wasSkipped && labelEl) labelEl.textContent = "Already running…";

        // Independent progress poller (separate cadence from finish poller).
        // Phase 3.2 (Milan P1): parallel phase labels + middle-dot separator
        // + token display name (Bitcoin not bitcoin) with 18-char truncation
        // to keep the button width from ballooning on long cg_ids.
        const PHASE_LABEL = {
            crypto:       "Crypto",
            crypto_retry: "Retrying",
            stocks:       "Stocks",   // drop "US": canvas is global, redundant
        };
        const _formatProgressToken = (raw) => {
            if (!raw) return "";
            // Prefer a friendly display name from the in-memory catalog.
            try {
                const t = (typeof tokenCatalogAll !== "undefined" && tokenCatalogAll.length
                           ? tokenCatalogAll
                           : (typeof tokenCatalog !== "undefined" ? tokenCatalog : null));
                if (t && Array.isArray(t)) {
                    const hit = t.find(x => x.id === raw
                        || String(x.id).toLowerCase() === String(raw).toLowerCase());
                    if (hit) {
                        // Crypto: prefer "Bitcoin"; stocks: ticker is already "MSTR".
                        const name = hit.asset_class === "us-stock"
                            ? (hit.symbol || raw)
                            : (hit.symbol || hit.name || raw);
                        return name.length > 18 ? name.slice(0, 17) + "…" : name;
                    }
                }
            } catch (_) {}
            // Fallback: title-case the id, then truncate.
            const s = String(raw);
            const pretty = s.charAt(0).toUpperCase() + s.slice(1);
            return pretty.length > 18 ? pretty.slice(0, 17) + "…" : pretty;
        };
        const progressPoll = async () => {
            if (!btn.disabled) return;   // refresh finished, stop polling
            const p = await API.getRefreshProgress().catch(() => null);
            if (p && p.phase && p.phase !== "idle" && p.total > 0) {
                const pct = Math.min(100, Math.round((p.current / p.total) * 100));
                if (barEl) barEl.style.width = pct + "%";
                if (labelEl) {
                    const phaseTxt = PHASE_LABEL[p.phase] || p.phase;
                    const tk = p.last_token ? ` · ${_formatProgressToken(p.last_token)}` : "";
                    // Phase 3.2 (Milan P1): middle-dot between phase and counter.
                    labelEl.textContent = `${phaseTxt} · ${p.current}/${p.total}${tk}`;
                }
            }
            // Phase 3.2 (Milan P1): the previous "Starting… → Refreshing…"
            // intermediate state was deleted — too noisy. Keep "Starting…"
            // (or "Already running…" for the skipped path) until real
            // progress numbers arrive, then jump straight to them.
            setTimeout(progressPoll, 1000);
        };
        setTimeout(progressPoll, 500);
        const start = Date.now();
        const TIMEOUT_MS = 10 * 60 * 1000;        // 10 minutes hard cap
        const POLL_MS = 2000;
        const poll = async () => {
            const status = await API.getSystemStatus().catch(() => null);
            const lr = status && status.last_update && status.last_update.last_run_summary;
            const finished = lr && lr.finished_at;
            const elapsed = Date.now() - start;
            // Phase 3.2 (architect P1): when our POST was skipped (another
            // refresh already running), finished_at will NOT advance from
            // *our* preFinished value — the in-flight run might already be
            // half-done with its own preFinished marker. In that case we
            // ride along the existing run by waiting for the progress dict
            // to return to "idle" (which fetcher.py's finally block always
            // does), instead of the finished_at jitter.
            let done;
            if (wasSkipped) {
                const pg = await API.getRefreshProgress().catch(() => null);
                done = pg && pg.phase === "idle";
            } else {
                done = finished && finished !== preFinished;
            }
            if (done || elapsed > TIMEOUT_MS) {
                await loadSystemStatus();
                await loadTokens();
                await loadRankings();
                // Phase 3.1 fix: after a manual or auto refresh, the
                // currently-selected token's K-line / indicators / market
                // panel must also be redrawn — otherwise the chart stays
                // frozen on whichever bar was last rendered. Without this
                // call, "Refresh" advances the topbar time but leaves the
                // candle, RSI, MACD, etc. visually stale.
                if (typeof currentToken !== "undefined" && currentToken) {
                    await onTokenChange();
                }
                btn.disabled = false;
                // Phase 3.1: reset the progress bar UI. Phase 3.2 (Milan P2):
                // toggle a class instead of just text so timeout state can be
                // visually distinct (red border + red label).
                if (barEl) barEl.style.width = "0%";
                const isTimeout = elapsed > TIMEOUT_MS && !done;
                btn.classList.toggle("refresh-btn-timeout", isTimeout);
                if (labelEl) labelEl.textContent = isTimeout
                                                   ? "Refresh (timeout)"
                                                   : "Refresh";
                return;
            }
            setTimeout(poll, POLL_MS);
        };
        setTimeout(poll, POLL_MS);
    }

    async function onBacktestRun() {
        if (!currentToken) return;
        const out = document.getElementById("backtest-stats");
        out.textContent = "running...";
        const data = await API.getBacktest(currentToken, 5, 20).catch(e => ({ result: { error: String(e) } }));
        const r = data.result || {};
        if (r.error) {
            out.textContent = `error: ${r.error}`;
            return;
        }
        out.innerHTML = `
            <div>CAGR: ${(r.cagr != null ? (r.cagr * 100).toFixed(2) + "%" : "--")}</div>
            <div>Sharpe: ${r.sharpe != null ? r.sharpe.toFixed(2) : "--"}</div>
            <div>Max DD: ${(r.max_drawdown != null ? (r.max_drawdown * 100).toFixed(2) + "%" : "--")}</div>
            <div>Trades: ${r.n_trades != null ? r.n_trades : "--"}</div>
            <div>Win rate: ${r.win_rate != null ? (r.win_rate * 100).toFixed(1) + "%" : "--"}</div>
        `;
        renderEquityCurve(r.equity_curve || []);
    }

    // P1-G: render the golden-cross equity curve into #backtest-equity-curve.
    // Re-uses the same TradingView v4 line-chart primitives the indicator
    // panels use, in the same dark palette. Equity is normalised so the
    // first point = 1.0 (the backtest engine already does this).
    function renderEquityCurve(curve) {
        const container = document.getElementById("backtest-equity-curve");
        if (!container) return;
        container.innerHTML = "";
        if (!curve || curve.length === 0) return;
        equityChart = LightweightCharts.createChart(container, {
            ...CandleChart._baseOpts(),
            width: container.clientWidth,
            height: container.clientHeight,
        });
        equitySeries = equityChart.addLineSeries({
            color: "#26a69a",
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: true,
            title: "Equity",
        });
        priceOverlaySeries = equityChart.addLineSeries({
            color: "#787b86",
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            priceScaleId: "price",
            title: "Price",
        });
        equityChart.priceScale("price").applyOptions({
            scaleMargins: { top: 0.1, bottom: 0.1 },
            visible: false,
        });
        const eqRows = [];
        const priceRows = [];
        const basePrice = curve[0] && curve[0].price ? curve[0].price : 1.0;
        for (const row of curve) {
            if (row.date == null || row.equity == null) continue;
            eqRows.push({ time: row.date, value: row.equity });
            if (row.price != null) {
                // normalised price overlay so both lines share visual scale
                priceRows.push({ time: row.date, value: row.price / basePrice });
            }
        }
        equitySeries.setData(eqRows);
        priceOverlaySeries.setData(priceRows);
        equityChart.timeScale().fitContent();
    }

    function wireResize() {
        let raf = null;
        window.addEventListener("resize", () => {
            if (raf) cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => {
                if (candleCtx) {
                    const c = document.getElementById("chart-candle");
                    candleCtx.chart.applyOptions({ width: c.clientWidth, height: c.clientHeight });
                }
                for (const fam of Object.keys(indicatorCharts)) {
                    const el = document.getElementById(`chart-${fam}`);
                    if (el) indicatorCharts[fam].applyOptions({ width: el.clientWidth, height: el.clientHeight });
                }
                if (equityChart) {
                    const el = document.getElementById("backtest-equity-curve");
                    if (el) equityChart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        wireResize();
        init();
    });
})();
