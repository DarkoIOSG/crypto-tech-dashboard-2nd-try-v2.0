// Indicator-panel chart builders.
// R8-3A: palette resolved from CSS variables at runtime; each chart keeps a
// small bookkeeping struct so retint() can update colours after theme toggle.

const IndicatorPanels = (() => {
    function readPalette() {
        const cs = getComputedStyle(document.documentElement);
        const v = (name, fallback) => (cs.getPropertyValue(name).trim() || fallback);
        return {
            bgSecondary: v("--bg-secondary",  "#1e222d"),
            textPrimary: v("--text-primary",  "#d1d4dc"),
            textMuted:   v("--text-secondary","#787b86"),
            grid:        v("--bg-tertiary",   "#2a2e39"),
            accentBlue:  v("--chart-ma-fast", "#2196f3"),
            accentOrange:v("--chart-ma-slow", "#ff9800"),
            accentGreen: v("--accent-green",  "#26a69a"),
            accentRed:   v("--accent-red",    "#ef5350"),
            accentYellow:v("--accent-yellow", "#f7c948"),
            accentPurple:v("--accent-purple", "#ab47bc"),
            muted:       v("--chart-volume",  "#5d6673"),
        };
    }

    function _toPoints(series) {
        if (!series) return [];
        const out = [];
        for (const r of series) {
            if (r.value === null || r.value === undefined || Number.isNaN(r.value)) continue;
            out.push({ time: r.date, value: r.value });
        }
        return out;
    }

    function _byPrefix(series, prefix) {
        if (!series) return null;
        const keys = Object.keys(series);
        if (series[prefix]) return series[prefix];
        for (const k of keys) {
            if (k === prefix || k.startsWith(prefix + "_")) return series[k];
        }
        return null;
    }

    function _smallChartOpts(p) {
        return {
            layout: {
                background: { type: "solid", color: p.bgSecondary },
                textColor: p.textPrimary,
                fontSize: 10,
                fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                attributionLogo: false,
            },
            grid: {
                vertLines: { color: p.grid, style: 0 },
                horzLines: { color: p.grid, style: 0 },
            },
            timeScale: {
                borderColor: p.grid,
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 4,
            },
            rightPriceScale: {
                borderColor: p.grid,
                minimumWidth: 72,   // R7-4 + uptick: keep OB/OS chip + tick lane clear
            },
            crosshair: {
                mode: 1,
                vertLine: { color: p.textMuted, width: 1, style: 3 },
                horzLine: { color: p.textMuted, width: 1, style: 3 },
            },
            handleScale: true,
            handleScroll: true,
        };
    }

    function _smallChart(container) {
        const p = readPalette();
        return LightweightCharts.createChart(container, {
            ..._smallChartOpts(p),
            width: container.clientWidth,
            height: container.clientHeight,
        });
    }

    // Each renderer returns { chart, retint() }. The retint closure captures
    // its line/series references and re-applies CSS-var colours on demand.

    function renderSMACross(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const fast = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        const slow = chart.addLineSeries({ color: p.accentOrange, lineWidth: 1 });
        fast.setData(_toPoints(_byPrefix(series, "sma_fast")));
        slow.setData(_toPoints(_byPrefix(series, "sma_slow")));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            fast.applyOptions({ color: q.accentBlue });
            slow.applyOptions({ color: q.accentOrange });
        };
        return { chart, retint };
    }

    function renderEMACross(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const fast = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        const slow = chart.addLineSeries({ color: p.accentOrange, lineWidth: 1 });
        fast.setData(_toPoints(_byPrefix(series, "ema_fast")));
        slow.setData(_toPoints(_byPrefix(series, "ema_slow")));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            fast.applyOptions({ color: q.accentBlue });
            slow.applyOptions({ color: q.accentOrange });
        };
        return { chart, retint };
    }

    function renderMACD(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const hist = chart.addHistogramSeries({ color: p.accentGreen, base: 0 });
        const line = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        const sig = chart.addLineSeries({ color: p.accentOrange, lineWidth: 1 });
        const rawHist = _toPoints(_byPrefix(series, "macd_hist"));
        function paintHist(palette) {
            hist.setData(rawHist.map(pt => ({
                time: pt.time,
                value: pt.value,
                color: pt.value >= 0 ? palette.accentGreen : palette.accentRed,
            })));
        }
        paintHist(p);
        line.setData(_toPoints(_byPrefix(series, "macd_line")));
        sig.setData(_toPoints(_byPrefix(series, "macd_signal")));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            line.applyOptions({ color: q.accentBlue });
            sig.applyOptions({ color: q.accentOrange });
            paintHist(q);
        };
        return { chart, retint };
    }

    function renderRSI(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const rsi = chart.addLineSeries({ color: p.accentPurple, lineWidth: 2 });
        rsi.setData(_toPoints(_byPrefix(series, "rsi")));
        rsi.createPriceLine({ price: 70, color: p.accentRed, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "OB" });
        rsi.createPriceLine({ price: 50, color: p.muted, lineWidth: 1, lineStyle: 1, axisLabelVisible: false });
        rsi.createPriceLine({ price: 30, color: p.accentGreen, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "OS" });
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            rsi.applyOptions({ color: q.accentPurple });
            // priceLines can't be recoloured via applyOptions; the slight
            // hue drift on toggle is acceptable since these are static refs.
        };
        return { chart, retint };
    }

    function renderRSIMR(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const s = chart.addLineSeries({ color: p.accentYellow, lineWidth: 1 });
        s.setData(_toPoints(_byPrefix(series, "rsi_mr_os_soft")));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            s.applyOptions({ color: q.accentYellow });
        };
        return { chart, retint };
    }

    function renderKDJ(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const k = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        const d = chart.addLineSeries({ color: p.accentOrange, lineWidth: 1 });
        const j = chart.addLineSeries({ color: p.accentPurple, lineWidth: 1 });
        k.setData(_toPoints(series["kdj_k"]));
        d.setData(_toPoints(series["kdj_d"]));
        j.setData(_toPoints(series["kdj_j"]));
        k.createPriceLine({ price: 80, color: p.accentRed, lineStyle: 2 });
        k.createPriceLine({ price: 20, color: p.accentGreen, lineStyle: 2 });
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            k.applyOptions({ color: q.accentBlue });
            d.applyOptions({ color: q.accentOrange });
            j.applyOptions({ color: q.accentPurple });
        };
        return { chart, retint };
    }

    function renderBollinger(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const upper = chart.addAreaSeries({
            topColor: "rgba(33, 150, 243, 0.10)",
            bottomColor: "rgba(33, 150, 243, 0.00)",
            lineColor: p.accentBlue,
            lineWidth: 1,
        });
        const mid = chart.addLineSeries({ color: p.muted, lineWidth: 1, lineStyle: 2 });
        const lower = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        upper.setData(_toPoints(_byPrefix(series, "bb_upper")));
        mid.setData(_toPoints(_byPrefix(series, "bb_mid")));
        lower.setData(_toPoints(_byPrefix(series, "bb_lower")));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            upper.applyOptions({ lineColor: q.accentBlue });
            mid.applyOptions({ color: q.muted });
            lower.applyOptions({ color: q.accentBlue });
        };
        return { chart, retint };
    }

    function renderVolumeSpike(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const ratio = chart.addLineSeries({ color: p.accentYellow, lineWidth: 1 });
        ratio.setData(_toPoints(_byPrefix(series, "vol_ratio")));
        ratio.createPriceLine({ price: 3.0, color: p.accentRed, lineStyle: 2, axisLabelVisible: true });
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            ratio.applyOptions({ color: q.accentYellow });
        };
        return { chart, retint };
    }

    function renderMomentum(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const palette = [p.accentBlue, p.accentGreen, p.accentOrange, p.accentPurple];
        const keys = ["mom_ret_5d", "mom_ret_10d", "mom_ret_20d", "mom_ret_30d"];
        const lines = keys.map((k, i) => {
            const s = chart.addLineSeries({ color: palette[i], lineWidth: 1 });
            s.setData(_toPoints(series[k]));
            return s;
        });
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            const np = [q.accentBlue, q.accentGreen, q.accentOrange, q.accentPurple];
            lines.forEach((s, i) => s.applyOptions({ color: np[i] }));
        };
        return { chart, retint };
    }

    function renderMeanReversion(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const z = chart.addLineSeries({ color: p.accentPurple, lineWidth: 1 });
        z.setData(_toPoints(series["mr_z_40_skip16"]));
        z.createPriceLine({ price: 2.0, color: p.accentRed, lineStyle: 2 });
        z.createPriceLine({ price: -2.0, color: p.accentGreen, lineStyle: 2 });
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            z.applyOptions({ color: q.accentPurple });
        };
        return { chart, retint };
    }

    function renderZScoreMA(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const dev = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        dev.setData(_toPoints(series["ma50_dev"]));
        const slope = chart.addLineSeries({ color: p.accentOrange, lineWidth: 1 });
        slope.setData(_toPoints(series["ma50_slope_20d"]));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            dev.applyOptions({ color: q.accentBlue });
            slope.applyOptions({ color: q.accentOrange });
        };
        return { chart, retint };
    }

    function renderPriceAppreciation(container, series) {
        const chart = _smallChart(container);
        const p = readPalette();
        const r10 = chart.addLineSeries({ color: p.accentBlue, lineWidth: 1 });
        const r20 = chart.addLineSeries({ color: p.accentOrange, lineWidth: 1 });
        r10.setData(_toPoints(series["price_ret_10d"]));
        r20.setData(_toPoints(series["price_ret_20d"]));
        const retint = () => {
            const q = readPalette();
            chart.applyOptions(_smallChartOpts(q));
            r10.applyOptions({ color: q.accentBlue });
            r20.applyOptions({ color: q.accentOrange });
        };
        return { chart, retint };
    }

    const renderers = {
        sma_cross: renderSMACross,
        ema_cross: renderEMACross,
        macd: renderMACD,
        rsi: renderRSI,
        rsi_mr: renderRSIMR,
        kdj: renderKDJ,
        bollinger: renderBollinger,
        volume_spike: renderVolumeSpike,
        momentum: renderMomentum,
        mean_reversion: renderMeanReversion,
        zscore_ma: renderZScoreMA,
        price_appreciation: renderPriceAppreciation,
    };

    function renderFamily(name, container, series) {
        const fn = renderers[name];
        if (!fn) return null;
        const built = fn(container, series);
        if (!built) return null;
        // Backwards-compat: app.js holds the underlying chart in indicatorCharts
        // and calls .remove() / .timeScale() / .applyOptions() on it. Attach
        // the retint closure as a non-enumerable property so theme toggle
        // can find it without changing the rest of the caller.
        try {
            Object.defineProperty(built.chart, "__retint", {
                value: built.retint, enumerable: false, configurable: true,
            });
        } catch (e) { /* harmless if chart object is frozen */ }
        return built.chart;
    }

    // R8-3A: re-tint all currently mounted indicator panels. `chartsMap`
    // is app.js's indicatorCharts (family -> chart instance with __retint).
    function retintAll(chartsMap) {
        if (!chartsMap) return;
        for (const family of Object.keys(chartsMap)) {
            const ch = chartsMap[family];
            if (ch && typeof ch.__retint === "function") {
                try { ch.__retint(); } catch (e) { /* skip bad panel */ }
            }
        }
    }

    return { renderFamily, retintAll, readPalette };
})();
