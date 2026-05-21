"""Final integration test (Phase done-check).

1. Launch uvicorn at 127.0.0.1:8080.
2. Wait 2s. Hit /health, /api/system/status. Expect 200.
3. Hit /api/tokens (must return 5), /api/scores (must compute).
4. Hit /, save HTML, grep "lightweight-charts" tag.
5. Kill server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYBIN = ROOT / "venv" / "bin" / "python"
HOST = "127.0.0.1"
PORT = 8080


def _wait_up(url: str, timeout_s: float = 25.0) -> bool:
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
    with urllib.request.urlopen(urllib.request.Request(url), timeout=15.0) as resp:
        return resp.status, resp.read()


def main() -> int:
    cmd = [
        str(PYBIN), "-m", "uvicorn", "backend.main:app",
        "--host", HOST, "--port", str(PORT), "--log-level", "warning",
    ]
    print(f"[itest] starting: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    rc = 1
    try:
        base = f"http://{HOST}:{PORT}"

        if not _wait_up(base + "/health"):
            print("[itest] FAIL: server did not start", flush=True)
            return 2
        time.sleep(2)

        # 1. health + system status
        st1, b1 = _get(base + "/health")
        print(f"[itest] /health              status={st1} body={b1[:120].decode()!r}")
        st2, b2 = _get(base + "/api/system/status")
        body2 = json.loads(b2.decode("utf-8"))
        print(f"[itest] /api/system/status   status={st2} token_count={body2.get('token_count')}")
        ok = (st1 == 200 and st2 == 200)

        # 2. tokens
        st3, b3 = _get(base + "/api/tokens")
        body3 = json.loads(b3.decode("utf-8"))
        n_tokens = body3.get("count", 0)
        print(f"[itest] /api/tokens          status={st3} count={n_tokens}")
        if st3 != 200 or n_tokens < 5:
            print(f"[itest] FAIL: expected >=5 tokens, got {n_tokens}")
            ok = False

        # 3. scores
        st4, b4 = _get(base + "/api/scores")
        body4 = json.loads(b4.decode("utf-8"))
        n_scores = body4.get("count", 0)
        print(f"[itest] /api/scores          status={st4} count={n_scores}")
        if st4 != 200 or n_scores < 5:
            print(f"[itest] FAIL: expected >=5 scores, got {n_scores}")
            ok = False
        # Show top 3
        for row in (body4.get("scores") or [])[:3]:
            print(f"             {row['cg_id']:12s} trend={row['trend_score']:.2f} reversal={row['reversal_score']:.2f}")

        # 4. /
        st5, b5 = _get(base + "/")
        html = b5.decode("utf-8", errors="replace")
        has_lib = "lightweight-charts" in html
        has_title = "IOSG Crypto Tech Dashboard" in html
        print(f"[itest] /                    status={st5} title={has_title} lib_tag={has_lib}")
        if st5 != 200 or not has_lib or not has_title:
            ok = False

        # Also probe one token's indicators and a single backtest
        st6, b6 = _get(base + "/api/indicators/bitcoin?days=60")
        ib = json.loads(b6.decode("utf-8"))
        print(f"[itest] /api/indicators/btc  status={st6} series_keys={len(ib.get('series') or {})}")
        if st6 != 200:
            ok = False

        st7, b7 = _get(base + "/api/backtest/bitcoin?fast=5&slow=20")
        bb = json.loads(b7.decode("utf-8"))
        r = bb.get("result", {})
        print(f"[itest] /api/backtest/btc    status={st7} cagr={r.get('cagr')!r} sharpe={r.get('sharpe')!r}")
        if st7 != 200:
            ok = False

        if ok:
            print("[itest] PASS", flush=True)
            rc = 0
        else:
            print("[itest] FAIL", flush=True)
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
