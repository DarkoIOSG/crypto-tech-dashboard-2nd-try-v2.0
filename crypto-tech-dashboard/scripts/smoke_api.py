"""Phase 3 — API smoke test.

Starts uvicorn in a background process, hits /health, /api/tokens, /api/scores.
Acceptance: all three return 200. Empty bodies are OK at this stage.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYBIN = ROOT / "venv" / "bin" / "python"
HOST = "127.0.0.1"
PORT = 8088  # dedicated smoke port to avoid clashing with the integration run


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
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return resp.status, resp.read()


def main() -> int:
    cmd = [
        str(PYBIN),
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ]
    print(f"[smoke_api] starting: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    rc = 1
    try:
        base = f"http://{HOST}:{PORT}"
        if not _wait_up(base + "/health", timeout_s=30.0):
            print("[smoke_api] FAIL: server did not come up in 30s", flush=True)
            return 2

        endpoints = ["/health", "/api/tokens", "/api/scores"]
        all_ok = True
        for ep in endpoints:
            status, body = _get(base + ep)
            preview = body[:200].decode("utf-8", errors="replace")
            print(f"[smoke_api] {ep:20s} status={status} body[:200]={preview}")
            if status != 200:
                all_ok = False

        if all_ok:
            print("[smoke_api] PASS", flush=True)
            rc = 0
        else:
            print("[smoke_api] FAIL: non-200 response above", flush=True)
            rc = 3
    finally:
        # Read any pending log output for debugging
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        out = b""
        if proc.stdout is not None:
            out = proc.stdout.read() or b""
        if out:
            print("---- server log tail ----")
            print(out[-2000:].decode("utf-8", errors="replace"))

    return rc


if __name__ == "__main__":
    sys.exit(main())
