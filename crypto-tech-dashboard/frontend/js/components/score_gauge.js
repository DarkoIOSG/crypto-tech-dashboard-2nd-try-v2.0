// P2-2 + R6-6: SVG semicircle "speedometer" gauge for trend / reversal / overall score.
// R8-3A: now reads palette from CSS variables so the gauge tints with the theme.

const ScoreGauge = (() => {
    const W = 220;
    const H = 124;
    const CX = W / 2;
    const CY = 100;
    const R = 75;
    const STROKE = 12;
    const _lastValues = new WeakMap();   // container -> last rendered value (for retint)

    function _palette() {
        const cs = getComputedStyle(document.documentElement);
        const v = (name, fallback) => (cs.getPropertyValue(name).trim() || fallback);
        return {
            muted:   v("--text-secondary",  "#787b86"),
            mutedBg: v("--bg-tertiary",     "#2a2e39"),
            track:   v("--border-subtle",   "#2a2e39"),
            border:  v("--border-primary",  "#363a45"),
            hub:     v("--bg-secondary",    "#1e222d"),
            empty:   v("--text-muted",      "#4c525e"),
            green:   v("--accent-green",    "#26a69a"),
            yellow:  v("--accent-yellow",   "#f7c948"),
            red:     v("--accent-red",      "#ef5350"),
        };
    }

    function _polar(deg, radius = R) {
        const rad = (deg - 90) * Math.PI / 180;
        return [CX + radius * Math.cos(rad), CY + radius * Math.sin(rad)];
    }

    function _arc(startDeg, endDeg) {
        const [sx, sy] = _polar(startDeg);
        const [ex, ey] = _polar(endDeg);
        const large = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
        const sweep = endDeg > startDeg ? 1 : 0;
        return `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${R} ${R} 0 ${large} ${sweep} ${ex.toFixed(2)} ${ey.toFixed(2)}`;
    }

    function _tierColor(v, pal) {
        if (v == null) return pal.muted;
        if (v >= 66) return pal.green;
        if (v >= 33) return pal.yellow;
        return pal.red;
    }

    function render(container, value) {
        if (!container) return;
        _lastValues.set(container, value);
        const pal = _palette();
        const v = (value == null || Number.isNaN(value)) ? null : Math.max(0, Math.min(100, value));
        const startDeg = -90;
        const endDeg = 90;
        const valDeg = v == null ? startDeg : startDeg + (v / 100) * (endDeg - startDeg);
        const color = _tierColor(v, pal);

        const trackPath = _arc(startDeg, endDeg);
        const valPath = v == null || v === 0 ? "" : _arc(startDeg, valDeg);

        const tickConfig = [
            { v: 0,   label: "0",   long: true },
            { v: 25,  label: null,  long: false },
            { v: 50,  label: "50",  long: true },
            { v: 75,  label: null,  long: false },
            { v: 100, label: "100", long: true },
        ];
        const tickSvg = tickConfig.map(t => {
            const deg = startDeg + (t.v / 100) * (endDeg - startDeg);
            const [x1, y1] = _polar(deg);
            const rOuter = R + STROKE / 2 + (t.long ? 7 : 4);
            const rad = (deg - 90) * Math.PI / 180;
            const x2 = CX + rOuter * Math.cos(rad);
            const y2 = CY + rOuter * Math.sin(rad);
            let line = `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}" stroke="${pal.muted}" stroke-width="${t.long ? 1.5 : 1}"/>`;
            if (t.label) {
                const rLabel = R + STROKE / 2 + 17;
                const lx = CX + rLabel * Math.cos(rad);
                const ly = CY + rLabel * Math.sin(rad);
                const anchor = t.v === 0 ? "start" : (t.v === 100 ? "end" : "middle");
                line += `<text x="${lx.toFixed(2)}" y="${(ly + 3).toFixed(2)}" text-anchor="${anchor}" font-size="9" fill="${pal.muted}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">${t.label}</text>`;
            }
            return line;
        }).join("");

        const [bx, by] = _polar(startDeg);
        const [ex, ey] = _polar(endDeg);
        const baseline = `<line x1="${bx.toFixed(2)}" y1="${by.toFixed(2)}" x2="${ex.toFixed(2)}" y2="${ey.toFixed(2)}" stroke="${pal.border}" stroke-width="1"/>`;

        const needleLen = R - 6;
        const needleBase = 4;
        const [nTipX, nTipY] = _polar(valDeg, needleLen);
        const axisRad = (valDeg - 90) * Math.PI / 180;
        const perpX = -Math.sin(axisRad);
        const perpY =  Math.cos(axisRad);
        const baseAX = CX + perpX * needleBase;
        const baseAY = CY + perpY * needleBase;
        const baseBX = CX - perpX * needleBase;
        const baseBY = CY - perpY * needleBase;
        const needleFill = v == null ? pal.empty : color;
        const needle = `<polygon points="${nTipX.toFixed(2)},${nTipY.toFixed(2)} ${baseAX.toFixed(2)},${baseAY.toFixed(2)} ${baseBX.toFixed(2)},${baseBY.toFixed(2)}" fill="${needleFill}" stroke="${needleFill}" stroke-linejoin="round" stroke-width="1"/>`;
        const hub = `<circle cx="${CX}" cy="${CY}" r="5" fill="${pal.hub}" stroke="${needleFill}" stroke-width="1.5"/>`;

        container.innerHTML = `
            <svg viewBox="0 0 ${W} ${H}" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="score gauge">
                <path d="${trackPath}" fill="none" stroke="${pal.track}" stroke-width="${STROKE}" stroke-linecap="round"/>
                ${valPath ? `<path d="${valPath}" fill="none" stroke="${color}" stroke-width="${STROKE}" stroke-linecap="round"/>` : ""}
                ${tickSvg}
                ${baseline}
                ${needle}
                ${hub}
            </svg>
        `;
    }

    // R8-3A: re-render all known gauges with current palette.
    function retintAll() {
        document.querySelectorAll(".score-gauge").forEach(el => {
            if (_lastValues.has(el)) render(el, _lastValues.get(el));
        });
    }

    return { render, retintAll };
})();
