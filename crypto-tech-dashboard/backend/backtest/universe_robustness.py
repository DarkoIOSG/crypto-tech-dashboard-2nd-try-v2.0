"""R8-2B: universe-wide indicator robustness — Phase-2 item 6.

For each (canonical strategy, token) pair, run the engine. Aggregate
per strategy: median / mean Sharpe, % positive, worst+best token,
median CAGR, n tokens. Assign a reliability badge ∈ {reliable,
caveats, unreliable} per the thresholds in Plan Part 3.1.

Caches results to local_data/robustness_cache/ JSON so the API
serves in <100ms. Hash invalidation: sha256 of sorted
(cg_id, mtime, size) across local_data/ohlcv/.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from backend.backtest.engine import run_backtest
from backend.backtest.strategies import CANONICAL_STRATEGIES
from backend.config import DATA_DIR


log = logging.getLogger(__name__)

CACHE_DIR = Path(DATA_DIR) / "robustness_cache"


def _ohlcv_hash() -> str:
    """Sha256 of sorted (cg_id, size, mtime) across local_data/ohlcv."""
    ohlcv_dir = Path(DATA_DIR) / "ohlcv"
    if not ohlcv_dir.exists():
        return ""
    rows = []
    for p in sorted(ohlcv_dir.glob("*.csv")):
        if p.name.endswith(".tmp"):
            continue
        st = p.stat()
        rows.append(f"{p.stem}:{st.st_size}:{int(st.st_mtime)}")
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _reliability(median_sharpe: float, pct_positive: float, worst: float) -> str:
    if median_sharpe >= 0.5 and pct_positive >= 60 and worst >= -1.0:
        return "reliable"
    if median_sharpe >= 0.2 or pct_positive >= 50:
        return "caveats"
    return "unreliable"


def run_universe_robustness(
    svc,
    strategies: Optional[dict] = None,
    asset_class: str = "crypto",
    min_history_days: int = 365,
    commission_bps: float = 5.0,
) -> Dict:
    """Run every canonical strategy on every token in the asset class.

    Returns {strategies: {name: aggregate_dict + per_token list},
             meta: {computed_at, asset_class, ohlcv_hash, ...}}.
    """
    strategies = strategies or CANONICAL_STRATEGIES
    started = time.time()
    log.info("run_universe_robustness: %s, %d strategies",
             asset_class, len(strategies))

    # Build candidate token list (crypto or stocks).
    candidates = []
    for t in svc.list_tokens(asset_class=asset_class):
        if not t.get("has_ohlcv"):
            continue
        df = svc.get_ohlcv(t["id"])
        if df is None or len(df) < min_history_days:
            continue
        candidates.append((t["id"], t.get("symbol"), df))

    log.info("  %d candidate tokens with history >= %d days",
             len(candidates), min_history_days)

    results: Dict[str, Dict] = {}
    for strat_name, (fn, params, label) in strategies.items():
        per_token: List[Dict] = []
        for cg_id, symbol, df in candidates:
            res = run_backtest(df, strategy=fn, strategy_params=params,
                               commission_bps=commission_bps)
            # Skip tokens with zero trades — they had no signal at all
            if res.n_trades == 0:
                continue
            per_token.append({
                "cg_id": cg_id,
                "symbol": symbol or cg_id.upper(),
                "sharpe": res.sharpe,
                "cagr": res.cagr,
                "max_dd": res.max_drawdown,
                "n_trades": res.n_trades,
                "win_rate": res.win_rate,
                "avg_trade_return": res.avg_trade_return,
            })
        if not per_token:
            results[strat_name] = {
                "label": label,
                "params": params,
                "median_sharpe": 0.0, "mean_sharpe": 0.0,
                "pct_positive": 0.0, "median_cagr": 0.0,
                "worst": None, "best": None,
                "reliability": "unreliable",
                "n_tokens": 0,
                "per_token": [],
            }
            continue
        sharpes = [r["sharpe"] for r in per_token]
        cagrs = [r["cagr"] for r in per_token]
        worst = min(per_token, key=lambda r: r["sharpe"])
        best = max(per_token, key=lambda r: r["sharpe"])
        median_sharpe = float(np.median(sharpes))
        mean_sharpe = float(np.mean(sharpes))
        pct_positive = float(100.0 * sum(1 for s in sharpes if s > 0) / len(sharpes))
        rel = _reliability(median_sharpe, pct_positive, float(worst["sharpe"]))
        results[strat_name] = {
            "label": label,
            "params": params,
            "median_sharpe": median_sharpe,
            "mean_sharpe": mean_sharpe,
            "pct_positive": pct_positive,
            "median_cagr": float(np.median(cagrs)),
            "worst": {"cg_id": worst["cg_id"], "symbol": worst["symbol"],
                      "sharpe": worst["sharpe"], "cagr": worst["cagr"]},
            "best": {"cg_id": best["cg_id"], "symbol": best["symbol"],
                     "sharpe": best["sharpe"], "cagr": best["cagr"]},
            "reliability": rel,
            "n_tokens": len(per_token),
            "per_token": sorted(per_token, key=lambda r: -r["sharpe"]),
        }
    elapsed = time.time() - started
    log.info("run_universe_robustness: done in %.1fs", elapsed)
    return {
        "strategies": results,
        "meta": {
            "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "asset_class": asset_class,
            "ohlcv_hash": _ohlcv_hash(),
            "n_candidates": len(candidates),
            "elapsed_seconds": round(elapsed, 1),
            "commission_bps": commission_bps,
            "min_history_days": min_history_days,
        },
    }


def write_cache(payload: Dict, asset_class: str = "crypto") -> None:
    """Persist a robustness run to local_data/robustness_cache/."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = CACHE_DIR / f"robustness_summary_{asset_class}.json"
    # Build the lightweight summary (no per_token detail)
    light = {
        "meta": payload["meta"],
        "strategies": {
            name: {k: v for k, v in s.items() if k != "per_token"}
            for name, s in payload["strategies"].items()
        },
    }
    tmp = summary_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(light, indent=2, sort_keys=True))
    tmp.replace(summary_path)
    # Per-strategy detail files
    for name, s in payload["strategies"].items():
        path = CACHE_DIR / f"robustness_{asset_class}_{name}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(s, indent=2, sort_keys=True))
        tmp.replace(path)
    # Meta file
    meta_path = CACHE_DIR / f"robustness_meta_{asset_class}.json"
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload["meta"], indent=2, sort_keys=True))
    tmp.replace(meta_path)
    log.info("robustness cache written to %s (%d strategies)",
             CACHE_DIR, len(payload["strategies"]))


def read_cache_summary(asset_class: str = "crypto") -> Optional[Dict]:
    path = CACHE_DIR / f"robustness_summary_{asset_class}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def read_cache_strategy(strategy_name: str, asset_class: str = "crypto") -> Optional[Dict]:
    path = CACHE_DIR / f"robustness_{asset_class}_{strategy_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def cache_is_fresh(asset_class: str = "crypto") -> bool:
    """True if the cache's ohlcv_hash matches today's hash."""
    meta_path = CACHE_DIR / f"robustness_meta_{asset_class}.json"
    if not meta_path.exists():
        return False
    meta = json.loads(meta_path.read_text())
    return meta.get("ohlcv_hash") == _ohlcv_hash()
