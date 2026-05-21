/* Phase 3 Module 8 (PM): lightweight toast notifications.
 * Used for hash-fallback notices (pasted #token=FOO not in catalog)
 * and unknown-token graceful-fail messages. Theme-aware via CSS vars. */
(function () {
    "use strict";

    const DEFAULTS = { kind: "info", duration: 4000 };
    let container = null;

    function ensureContainer() {
        if (container && document.body.contains(container)) return container;
        container = document.createElement("div");
        container.className = "toast-container";
        container.setAttribute("role", "status");
        container.setAttribute("aria-live", "polite");
        document.body.appendChild(container);
        return container;
    }

    function show(message, opts) {
        if (!message) return null;
        const o = Object.assign({}, DEFAULTS, opts || {});
        const root = ensureContainer();

        const node = document.createElement("div");
        node.className = `toast toast-${o.kind}`;

        const msg = document.createElement("span");
        msg.className = "toast-msg";
        msg.textContent = message;
        node.appendChild(msg);

        const close = document.createElement("button");
        close.className = "toast-close";
        close.type = "button";
        close.setAttribute("aria-label", "Dismiss");
        close.textContent = "×";
        node.appendChild(close);

        let timer = null;
        function dismiss() {
            if (timer) { clearTimeout(timer); timer = null; }
            node.classList.add("toast-leaving");
            setTimeout(() => {
                if (node.parentNode) node.parentNode.removeChild(node);
            }, 200);
        }
        close.addEventListener("click", dismiss);

        root.appendChild(node);
        // Trigger entrance animation on next frame.
        requestAnimationFrame(() => node.classList.add("toast-entered"));

        if (o.duration > 0) timer = setTimeout(dismiss, o.duration);
        return { dismiss };
    }

    window.Toast = { show: show };
})();
