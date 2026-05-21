// P2-3: tiny inline SVG sparkline for the ranking sidebar.
// R8-3A: stroke + fill read from CSS variables so the spark tints with the theme.

const Sparkline = (() => {
    const W = 60;
    const H = 18;
    const PAD = 1.5;

    function _palette() {
        const cs = getComputedStyle(document.documentElement);
        const v = (name, fallback) => (cs.getPropertyValue(name).trim() || fallback);
        return {
            up:   v("--accent-green", "#26a69a"),
            down: v("--accent-red",   "#ef5350"),
        };
    }

    function _alpha(hex, a) {
        const h = (hex || "").replace("#", "").trim();
        if (h.length !== 6 && h.length !== 3) return hex;
        const full = h.length === 3 ? h.split("").map(c => c + c).join("") : h;
        const r = parseInt(full.slice(0, 2), 16);
        const g = parseInt(full.slice(2, 4), 16);
        const b = parseInt(full.slice(4, 6), 16);
        return `rgba(${r},${g},${b},${a})`;
    }

    function render(container, values) {
        if (!container) return;
        if (!Array.isArray(values) || values.length < 2) {
            container.innerHTML = "";
            return;
        }
        const pal = _palette();
        const min = Math.min(...values);
        const max = Math.max(...values);
        const span = (max - min) || 1;
        const stepX = (W - PAD * 2) / (values.length - 1);
        const pts = values.map((v, i) => {
            const x = PAD + i * stepX;
            const y = H - PAD - ((v - min) / span) * (H - PAD * 2);
            return `${x.toFixed(2)},${y.toFixed(2)}`;
        }).join(" ");
        const up = values[values.length - 1] >= values[0];
        const stroke = up ? pal.up : pal.down;
        const fill = _alpha(stroke, 0.15);
        const areaPts = `${PAD.toFixed(2)},${(H - PAD).toFixed(2)} ${pts} ${(W - PAD).toFixed(2)},${(H - PAD).toFixed(2)}`;
        container.innerHTML = `
            <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <polygon points="${areaPts}" fill="${fill}" stroke="none"/>
                <polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1" stroke-linejoin="round" stroke-linecap="round"/>
            </svg>
        `;
    }

    return { render };
})();
