"""Full Top-200 initial load — runs `Fetcher.run_full_initial_load(top_n=200, history_days=1095)`.

Streams progress to stdout/stderr; appends a single summary line to PROGRESS.md
and writes the final summary dict to BUILD_STATUS.json.

Per Plan §7: expected runtime 40–70 minutes for a cold initial load.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from backend.config import DATA_DIR, METADATA_DIR  # noqa: E402
from backend.data.coingecko_client import CoinGeckoClient  # noqa: E402
import backend.data.data_validator as dv  # noqa: E402
from backend.data.exchange_client import ExchangeOHLCVClient  # noqa: E402
from backend.data.fetcher import Fetcher  # noqa: E402
from backend.data.local_store import LocalStore  # noqa: E402
from backend.data.symbol_mapping import SymbolMapper  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scripts.full_initial_load")


class _ValidatorShim:
    def validate_ohlcv(self, df):
        return dv.validate_ohlcv(df)


def main() -> int:
    started = datetime.utcnow().isoformat() + "Z"
    log.info("=== full initial load started ===")

    cg = CoinGeckoClient()
    ex = ExchangeOHLCVClient()
    ex.load_markets_all()
    mapper = SymbolMapper(METADATA_DIR, ex)
    store = LocalStore(DATA_DIR)
    fetcher = Fetcher(ex, cg, mapper, store, _ValidatorShim())

    t0 = time.time()
    summary = fetcher.run_full_initial_load(top_n=200, history_days=1095)
    elapsed_s = time.time() - t0

    summary["elapsed_seconds"] = round(elapsed_s, 1)
    summary["elapsed_minutes"] = round(elapsed_s / 60, 1)

    log.info("=== full initial load done in %.1fs (%.1fm) ===", elapsed_s, elapsed_s / 60)
    log.info("summary: %s", json.dumps(summary, default=str))

    # Persist machine-readable result.
    status_path = REPO.parent / "BUILD_STATUS.json"
    payload = {
        "phase": "done",
        "step": "full_initial_load",
        "ok": summary.get("status") == "ok",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
    }
    status_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("wrote %s", status_path)

    # Append one line to PROGRESS.md.
    progress_path = REPO.parent / "PROGRESS.md"
    line = (
        f"\n## Full initial load ({datetime.now().strftime('%H:%M')})\n"
        f"- started: {started}\n"
        f"- elapsed: {summary['elapsed_minutes']} min\n"
        f"- result: success={summary.get('success', 0)} "
        f"fallback={summary.get('fallback', 0)} "
        f"failed={summary.get('failed', 0)} "
        f"universe_size={summary.get('universe_size', 0)}\n"
    )
    with progress_path.open("a", encoding="utf-8") as f:
        f.write(line)

    print(f"\nDONE: success={summary.get('success')} fallback={summary.get('fallback')} failed={summary.get('failed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
