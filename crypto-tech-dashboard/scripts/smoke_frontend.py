"""Phase 4 — Frontend smoke test.

Starts uvicorn, fetches /, /lib/lightweight-charts.standalone.production.js,
/css/styles.css and /js/app.js. Confirms HTML has the title, JS is >100KB.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYBIN = ROOT / "venv" / "bin" / "python"
HOST = "127.0.0.1"
PORT = 8089


def _wait_up(url: str, timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if 200 <= resp.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=10.0) as resp:
        return resp.status, resp.read()


def main() -> int:
    cmd = [
        str(PYBIN), "-m", "uvicorn", "backend.main:app",
        "--host", HOST, "--port", str(PORT), "--log-level", "warning",
    ]
    print(f"[smoke_fe] launching: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    rc = 1
    try:
        base = f"http://{HOST}:{PORT}"
        if not _wait_up(base + "/health"):
            print("[smoke_fe] FAIL: server did not start", flush=True)
            return 2

        ok = True

        st, body = _get(base + "/")
        body_str = body.decode("utf-8", errors="replace")
        has_title = "IOSG Crypto Tech Dashboard" in body_str
        has_lib_tag = "lightweight-charts.standalone.production.js" in body_str
        print(f"[smoke_fe] /                          status={st} len={len(body)} title={has_title} lib_tag={has_lib_tag}")
        if st != 200 or not has_title or not has_lib_tag:
            ok = False

        st, body = _get(base + "/lib/lightweight-charts.standalone.production.js")
        size_kb = len(body) // 1024
        print(f"[smoke_fe] /lib/lightweight-charts... status={st} size={size_kb}KB")
        if st != 200 or len(body) < 100 * 1024:
            ok = False

        st, body = _get(base + "/css/styles.css")
        print(f"[smoke_fe] /css/styles.css            status={st} len={len(body)}")
        if st != 200:
            ok = False

        st, body = _get(base + "/js/app.js")
        print(f"[smoke_fe] /js/app.js                 status={st} len={len(body)}")
        if st != 200:
            ok = False

        if ok:
            print("[smoke_fe] PASS", flush=True)
            rc = 0
        else:
            print("[smoke_fe] FAIL: see above", flush=True)
            rc = 3
    finally:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        if proc.stdout:
            tail = proc.stdout.read() or b""
            if tail:
                print("---- server log tail ----")
                print(tail[-1500:].decode("utf-8", errors="replace"))

    return rc


if __name__ == "__main__":
    sys.exit(main())
