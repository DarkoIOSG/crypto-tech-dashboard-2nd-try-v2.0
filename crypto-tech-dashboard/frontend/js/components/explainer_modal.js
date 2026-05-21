// R8-2C: explainer modal. Open from any .info-mark. Marks with
// data-explainer=<kind> use the backend explainer payload; title-only marks
// are converted into a modal so every visible `?` is both hoverable and
// clickable.

const ExplainerModal = (() => {
    let _cache = null;
    let _delegated = false;

    async function _load() {
        if (_cache) return _cache;
        const resp = await API.getScoringExplainers().catch(() => null);
        if (resp && resp.explainers) {
            _cache = resp.explainers;
        } else {
            _cache = {};
        }
        return _cache;
    }

    function _ensureModal() {
        let m = document.getElementById("explainer-modal");
        if (m) return m;
        m = document.createElement("div");
        m.id = "explainer-modal";
        m.className = "explainer-modal";
        m.hidden = true;
        m.innerHTML = `
            <div class="explainer-backdrop"></div>
            <div class="explainer-body">
                <button class="explainer-close" aria-label="Close">×</button>
                <div class="explainer-content"></div>
            </div>
        `;
        document.body.appendChild(m);
        m.querySelector(".explainer-backdrop").addEventListener("click", close);
        m.querySelector(".explainer-close").addEventListener("click", close);
        document.addEventListener("keydown", e => {
            if (e.key === "Escape") close();
        });
        return m;
    }

    function close() {
        const m = document.getElementById("explainer-modal");
        if (m) m.hidden = true;
    }

    function _escapeHtml(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function _titleFromContext(el) {
        const ctx = el.closest(
            "h2,h3,summary,li,.score-badge,.market-tile-label,.sidebar-head,.data-coverage-label,.fallback-stat,.exchange-health"
        );
        const raw = (ctx && ctx.textContent ? ctx.textContent : "Indicator Help")
            .replace(/\?/g, " ")
            .replace(/\s+/g, " ")
            .trim();
        return raw || "Indicator Help";
    }

    function _titleTextToHtml(text) {
        const normalized = String(text || "").replace(/\s+/g, " ").trim();
        if (!normalized) return "";
        // Split long native-title text into readable paragraphs. The source
        // strings already use semantic labels like DEFINITION / FORMULA /
        // INTERPRETATION; keep them visible instead of dumping one wall of text.
        const parts = normalized
            .split(/(?=\b(?:DEFINITION|FORMULA|COMPUTATION|INPUT SIGNALS|INTERPRETATION|CONSEQUENCES|WHY THIS HAPPENS|SOURCE|DATA|SORT MODES|SPARKLINE|CLICK|EXECUTION|FRICTION|REPORTS|RULE|THE 9 STRATEGIES|AGGREGATION|RELIABILITY BADGE|PARAMETERS|SHOWN FIELDS|WEIGHT RATIONALE|OVERALL WEIGHT|FORMAT OF THE FALLBACK)\b:)/g)
            .map(s => s.trim())
            .filter(Boolean);
        return parts.map(p => `<p class="explainer-oneline">${_escapeHtml(p)}</p>`).join("");
    }

    function openTitle(title, heading) {
        const html = _titleTextToHtml(title);
        if (!html) return;
        const m = _ensureModal();
        const content = m.querySelector(".explainer-content");
        content.innerHTML = `
            <h2 class="explainer-title">${_escapeHtml(heading || "Indicator Help")}</h2>
            ${html}
        `;
        m.hidden = false;
    }

    async function open(kind) {
        await _load();
        const data = (_cache || {})[kind];
        if (!data) return;
        const m = _ensureModal();
        const content = m.querySelector(".explainer-content");

        let html = `
            <h2 class="explainer-title">${data.title}</h2>
            <p class="explainer-oneline">${data.one_line || ""}</p>
            <pre class="explainer-formula">${data.formula_md || ""}</pre>
        `;
        if (data.signal_table && data.signal_table.length) {
            html += `<h3>Constituents</h3>
                <table class="explainer-table">
                  <thead><tr><th>Label</th><th>Key</th><th>Weight</th></tr></thead>
                  <tbody>`;
            data.signal_table.forEach(s => {
                html += `<tr><td>${s.label}</td><td><code>${s.key}</code></td><td class="num">${s.weight}</td></tr>`;
            });
            html += `</tbody></table>`;
        }
        if (data.strengths && data.strengths.length) {
            html += `<h3>Strengths</h3><ul class="explainer-list">`;
            data.strengths.forEach(s => html += `<li>${s}</li>`);
            html += `</ul>`;
        }
        if (data.weaknesses && data.weaknesses.length) {
            html += `<h3>Weaknesses</h3><ul class="explainer-list">`;
            data.weaknesses.forEach(s => html += `<li>${s}</li>`);
            html += `</ul>`;
        }
        if (data.interpretation) {
            html += `<h3>Interpretation</h3><ul class="explainer-list">`;
            for (const [range, text] of Object.entries(data.interpretation)) {
                html += `<li><strong>${range.replace(/_/g, "–")}</strong>: ${text}</li>`;
            }
            html += `</ul>`;
        }
        content.innerHTML = html;
        m.hidden = false;
    }

    async function _openFromElement(el) {
        const kind = el.getAttribute("data-explainer");
        if (kind) {
            await open(kind);
            return;
        }
        const title = el.getAttribute("title")
            || (el.closest("[title]") && el.closest("[title]").getAttribute("title"))
            || "";
        openTitle(title, _titleFromContext(el));
    }

    function _wireDelegatedEvents() {
        if (_delegated) return;
        _delegated = true;
        document.addEventListener("click", (e) => {
            const el = e.target && e.target.closest ? e.target.closest(".info-mark") : null;
            if (!el) return;
            e.preventDefault();
            e.stopPropagation();
            _openFromElement(el);
        }, true);
        document.addEventListener("keydown", (e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            const el = e.target && e.target.closest ? e.target.closest(".info-mark") : null;
            if (!el) return;
            e.preventDefault();
            e.stopPropagation();
            _openFromElement(el);
        }, true);
    }

    // Wire all .info-mark elements. Click handling is delegated at document
    // level so dynamically-inserted marks (topbar close-only, sleeve rows,
    // ranking warnings added after async fetches) work without rebinding.
    function wire() {
        _wireDelegatedEvents();
        document.querySelectorAll(".info-mark").forEach(el => {
            el.dataset.explainerWired = "1";
            el.style.cursor = "pointer";
            el.setAttribute("role", "button");
            if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
        });
    }

    return { open, openTitle, close, wire };
})();
