// IOSG access gate — frontend-only password check. Hard-coded "IOSG"
// (4 uppercase letters). On success: localStorage.iosg-auth = 'ok' →
// permanently skip the gate until cache is cleared. This is NOT a
// real auth system — it's a "private link" guard for controlled demos.
// Public-facing deployments need server-side auth (TODO Phase 3).

(function () {
    const CODE = "IOSG";
    const form = document.getElementById("login-form");
    const input = document.getElementById("login-input");
    const err = document.getElementById("login-error");

    if (!form || !input) return;

    // Auto-focus the input on load.
    setTimeout(() => input.focus(), 60);

    function fail() {
        err.hidden = false;
        form.classList.add("shake");
        input.select();
        setTimeout(() => form.classList.remove("shake"), 420);
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        const v = (input.value || "").trim();
        if (v === CODE) {
            try { localStorage.setItem("iosg-auth", "ok"); } catch (e) {}
            err.hidden = true;
            location.replace("/");
        } else {
            fail();
        }
    });

    // Pressing Esc clears the input.
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            input.value = "";
            err.hidden = true;
            input.focus();
        }
    });
})();
