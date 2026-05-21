"""R8-1A: boot-time integrity check for the local data folder.

Walks every OHLCV CSV under DATA_DIR/ohlcv/ and flags issues:
  1. file size > 0
  2. CSV readable by pandas
  3. header matches local_store.OHLCV_COLUMNS
  4. row count >= MIN_OHLCV_ROWS
  5. last_date within `freshness_days` of today (for active tokens)
  6. validate_ohlcv() returns no issues

Corrupt CSVs are MOVED (not deleted) to DATA_DIR/quarantine/<cg_id>.<isodate>.csv
so an operator can inspect or restore. The full report is persisted to
DATA_DIR/metadata/data_integrity_log.json on every boot.

This is a permitted try/except site (boundary code reading external state).
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backend.config import DATA_DIR, MIN_OHLCV_ROWS
from backend.data.data_validator import validate_ohlcv
from backend.data.local_store import OHLCV_COLUMNS


def _load_cg_offset_summary() -> Dict:
    """Read cg_offset.json (written by CoinGeckoClient.validate_cg_offset
    at boot) and return the headline cross-source alignment fields. Plan
    §3.5 (Phase 1): cross-source consistency between Binance and CoinGecko
    is verified at boot; this surfaces the result alongside the per-file
    integrity report so operators see one pane of glass."""
    path = Path(DATA_DIR) / "metadata" / "cg_offset.json"
    if not path.exists():
        return {"available": False, "reason": "cg_offset.json not yet written"}
    try:
        d = json.loads(path.read_text())
    except Exception as exc:  # boundary
        return {"available": False, "reason": f"cg_offset.json unreadable: {exc}"}
    headline_pct = d.get("btc_max_diff_pct")
    offset_days = d.get("offset_days")
    # Plan tolerance: < 1% mean abs deviation is "aligned"; 1-5% is "warn";
    # ≥ 5% means the Tier-4 fallback path would inject visibly wrong
    # prices and the operator should investigate.
    if headline_pct is None:
        status = "unknown"
    elif headline_pct < 1.0:
        status = "aligned"
    elif headline_pct < 5.0:
        status = "warn"
    else:
        status = "misaligned"
    return {
        "available": True,
        "status": status,
        "offset_days": offset_days,
        "btc_max_diff_pct": headline_pct,
        "exchange": d.get("exchange"),
        "method": d.get("method"),
        "detected_at": d.get("detected_at"),
        "overlap_days": d.get("btc_overlap_days"),
    }


_DEFAULT_FRESHNESS_DAYS = 14


def _quarantine_dir() -> Path:
    out = Path(DATA_DIR) / "quarantine"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _quarantine_one(path: Path, reason: str) -> Path:
    """Move a corrupt CSV to quarantine. Returns the new path."""
    qdir = _quarantine_dir()
    stamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    target = qdir / f"{path.stem}.{stamp}.{reason}.csv"
    shutil.move(str(path), str(target))
    return target


def _check_one_csv(path: Path, freshness_days: int) -> Tuple[List[str], Optional[str]]:
    """Return (issues, last_date_iso). issues is empty when the file is clean."""
    issues: List[str] = []
    last_date: Optional[str] = None

    if not path.exists():
        return (["file_missing"], None)
    if path.stat().st_size == 0:
        return (["empty_file"], None)

    try:
        df = pd.read_csv(path)
    except Exception as exc:  # boundary: external CSV may be malformed
        return ([f"unreadable_csv: {type(exc).__name__}"], None)

    if df is None or len(df) == 0:
        return (["empty_dataframe"], None)

    # Header — every expected column must exist (order doesn't matter).
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        issues.append(f"missing_columns: {missing}")

    # Row count floor.
    if len(df) < MIN_OHLCV_ROWS:
        issues.append(f"too_few_rows: {len(df)} < {MIN_OHLCV_ROWS}")

    # Last date + freshness (only check if date column parseable).
    if "date" in df.columns:
        parsed = pd.to_datetime(df["date"], errors="coerce")
        valid = parsed[parsed.notna()]
        if len(valid) > 0:
            last_date_ts = valid.max()
            last_date = last_date_ts.strftime("%Y-%m-%d")
            today = _dt.datetime.now().date()
            age = (today - last_date_ts.date()).days
            if age > freshness_days:
                issues.append(f"stale_data: last_date={last_date}, age_days={age}")

    # validate_ohlcv full deep check (only when basic schema looks plausible).
    if not missing and len(df) > 0:
        deep_issues = validate_ohlcv(df)
        if deep_issues:
            issues.append("validate_ohlcv: " + " | ".join(deep_issues[:3]))

    return (issues, last_date)


def verify_local_data_integrity(
    *,
    freshness_days: int = _DEFAULT_FRESHNESS_DAYS,
    quarantine_corrupt: bool = True,
    write_log: bool = True,
) -> Dict:
    """Walk every OHLCV CSV and report. Returns the summary dict.

    Arguments:
        freshness_days   — last_date must be within this many days of today;
                           otherwise the token is flagged stale (but NOT
                           quarantined — staleness is recoverable via daily
                           update, not file corruption).
        quarantine_corrupt — if True, move unreadable / empty / missing-column
                           CSVs to DATA_DIR/quarantine/. Stale tokens are
                           never quarantined.
        write_log        — if True, persist the summary to
                           DATA_DIR/metadata/data_integrity_log.json (overwriting).
    """
    ohlcv_dir = Path(DATA_DIR) / "ohlcv"
    ohlcv_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict = {
        "checked_at": _dt.datetime.now().isoformat(),
        # Do not persist absolute host paths here. This file often gets
        # zipped or copied for handoff, and an absolute host path leaks the
        # operator's local account name and folder layout.
        "data_dir": "DATA_DIR",
        "total_files": 0,
        "clean": 0,
        "stale": [],
        "quarantined": [],
        "issues_by_token": {},
        # Cross-Plan P2: lift the most-recent cross-source date alignment
        # result (Binance vs CoinGecko close, BTC 30d overlap) into the
        # integrity log so operators see it without having to open a second
        # file. Source: cg_offset.json (populated by validate_cg_offset at
        # boot). Plan §3.5 cross-source consistency.
        "cross_source_alignment": _load_cg_offset_summary(),
    }

    # Categories of issues that DO warrant quarantine.
    corrupt_keywords = ("empty_file", "unreadable_csv", "missing_columns", "empty_dataframe")

    for csv_path in sorted(ohlcv_dir.glob("*.csv")):
        if csv_path.name.endswith(".tmp"):
            continue
        cg_id = csv_path.stem
        summary["total_files"] += 1
        issues, last_date = _check_one_csv(csv_path, freshness_days)

        if not issues:
            summary["clean"] += 1
            continue

        summary["issues_by_token"][cg_id] = {
            "issues": issues,
            "last_date": last_date,
        }

        is_corrupt = any(any(k in i for k in corrupt_keywords) for i in issues)
        if is_corrupt and quarantine_corrupt:
            try:
                new_path = _quarantine_one(csv_path, reason="corrupt")
                summary["quarantined"].append(
                    {"cg_id": cg_id, "moved_to": str(new_path)}
                )
            except Exception as exc:  # boundary: shutil may fail on permissions
                summary["issues_by_token"][cg_id]["issues"].append(
                    f"quarantine_failed: {type(exc).__name__}"
                )
        else:
            # Stale but not corrupt — leave on disk, just flag.
            summary["stale"].append(cg_id)

    if write_log:
        log_path = Path(DATA_DIR) / "metadata" / "data_integrity_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = log_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(summary, indent=2, sort_keys=True))
        tmp.replace(log_path)

    return summary
