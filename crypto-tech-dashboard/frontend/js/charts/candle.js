// Candle / main K-line chart wrapper.
// R8-3A: palette read from CSS variables at runtime so the chart can be
// re-tinted on theme toggle without destroy/recreate (preserves zoom state).

const CandleChart = (() => {
    function readPalette() {
        const cs = getComputedStyle(document.documentElement);
        const v = (name, fallback) => (cs.getPropertyValue(name).trim() || fallback);
        return {
            bgPrimary:   v("--bg-primary",      "#131722"),
            bgSecondary: v("--bg-secondary",    "#1e222d"),
            textPrimary: v("--text-primary",    "#d1d4dc"),
            textMuted:   v("--text-secondary",  "#787b86"),
            grid:        v("--bg-tertiary",     "#2a2e39"),
            border:      v("--border-primary",  "#363a45"),
            up:          v("--chart-candle-up", "#26a69a"),
            down:        v("--chart-candle-down", "#ef5350"),
            volume:      v("--chart-volume",    "#5d6673"),
        };
    }

    function _baseOpts(p) {
        p = p || readPalette();
        return {
            layout: {
                background: { type: "solid", color: p.bgSecondary },
                textColor: p.textPrimary,
                fontSize: 12,
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
                rightOffset: 6,
            },
            rightPriceScale: {
                borderColor: p.grid,
                scaleMargins: { top: 0.08, bottom: 0.22 },
                minimumWidth: 64,
            },
            crosshair: {
                mode: 1,
                vertLine: { color: p.textMuted, width: 1, style: 3, labelBackgroundColor: p.border },
                horzLine: { color: p.textMuted, width: 1, style: 3, labelBackgroundColor: p.border },
            },
        };
    }

    function create(container) {
        const p = readPalette();
        const chart = LightweightCharts.createChart(container, {
            ..._baseOpts(p),
            width: container.clientWidth,
            height: container.clientHeight,
        });
        const series = chart.addCandlestickSeries({
            upColor: p.up,
            downColor: p.down,
            wickUpColor: p.up,
            wickDownColor: p.down,
            borderVisible: false,
        });
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: "volume" },
            priceScaleId: "vol",
            color: p.volume,
        });
        chart.priceScale("vol").applyOptions({
            scaleMargins: { top: 0.78, bottom: 0 },
        });
        return { chart, series, volumeSeries, _ohlcv: null };
    }

    function setData(ctx, ohlcv) {
        ctx._ohlcv = ohlcv;
        const p = readPalette();
        const candles = [];
        const volumes = [];
        let lastDir = null;
        for (const row of ohlcv) {
            if (row.open === null || row.close === null) continue;
            candles.push({
                time: row.date,
                open: row.open,
                high: row.high,
                low: row.low,
                close: row.close,
            });
            const dirUp = row.close >= row.open;
            const col = dirUp ? _withAlpha(p.up, 0.55) : _withAlpha(p.down, 0.55);
            volumes.push({ time: row.date, value: row.volume || 0, color: col });
            lastDir = dirUp;
        }
        ctx.series.setData(candles);
        ctx.volumeSeries.setData(volumes);
        if (lastDir != null) {
            const dirColor = lastDir ? p.up : p.down;
            ctx.series.applyOptions({
                priceLineColor: dirColor,
                priceLineVisible: true,
                lastValueVisible: true,
            });
            ctx.volumeSeries.applyOptions({
                priceLineColor: dirColor,
                priceLineVisible: false,
                lastValueVisible: true,
            });
        }
    }

    // R8-3A: re-apply current theme to an existing chart without recreating it
    // (preserves user's zoom + pan state on theme toggle).
    function retint(ctx) {
        if (!ctx || !ctx.chart) return;
        const p = readPalette();
        ctx.chart.applyOptions(_baseOpts(p));
        ctx.series.applyOptions({
            upColor: p.up, downColor: p.down,
            wickUpColor: p.up, wickDownColor: p.down,
        });
        ctx.volumeSeries.applyOptions({ color: p.volume });
        // Re-paint volume bar colours (they're per-bar so applyOptions alone won't update them).
        if (ctx._ohlcv) setData(ctx, ctx._ohlcv);
    }

    function _withAlpha(hex, a) {
        const h = (hex || "").replace("#", "").trim();
        if (h.length !== 6 && h.length !== 3) return hex;
        const full = h.length === 3 ? h.split("").map(c => c + c).join("") : h;
        const r = parseInt(full.slice(0, 2), 16);
        const g = parseInt(full.slice(2, 4), 16);
        const b = parseInt(full.slice(4, 6), 16);
        return `rgba(${r},${g},${b},${a})`;
    }

    return { create, setData, retint, _baseOpts, readPalette };
})();
