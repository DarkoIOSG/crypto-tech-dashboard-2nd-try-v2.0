"""Local CSV/JSON cache management for OHLCV, market-cap, and metadata.

Per PLAN section 3.2 ("local file cache architecture"):
- CoinGecko-ID-based filenames in `local_data/ohlcv/`.
- Atomic writes via `.tmp + os.replace()` (rename is atomic on a single
  filesystem on POSIX and Windows >=Vista).
- No partial writes; never write directly to the destination path.

Hard rule (A2): try/except is permitted ONLY inside `_atomic_write_csv` and
its small JSON sibling for `.tmp` cleanup on failure. No other function in
this module uses try/except.

Contract for A1 (Fetcher Author):
    from backend.data.local_store import LocalStore
    store = LocalStore(data_dir)
    store.read_ohlcv(cg_id) -> pd.DataFrame | None
    store.write_ohlcv(cg_id, df, source) -> None
    store.append_ohlcv(cg_id, new_rows) -> int
    store.write_mcap_snapshot(date, df) -> None
    store.write_top200_current(df) -> None
    store.read_last_update() -> dict
    store.write_last_update(d) -> None
    store.list_ohlcv_ids() -> list[str]
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


# Canonical column order for ohlcv/<cg_id>.csv (PLAN section 3.2).
OHLCV_COLUMNS: List[str] = ["date", "open", "high", "low", "close", "volume", "source"]

LAST_UPDATE_FILENAME = "last_update.json"
DATA_INTEGRITY_LOG_FILENAME = "data_integrity_log.json"
TOP200_CURRENT_FILENAME = "top200_current.csv"
SCORES_HISTORY_FILENAME = "scores_history.csv"
SCORES_HISTORY_COLUMNS: List[str] = [
    "date",
    "cg_id",
    "trend_score",
    "reversal_score",
    "trend_cs_percentile",
    "reversal_cs_percentile",
    # R8-2A: overall composite (added Phase 2). Older rows from before the
    # extension carry NaN here; readers tolerate the gap via fillna(None).
    "overall_score",
    "overall_cs_percentile",
]


class LocalStore:
    """File-backed cache rooted at `data_dir` (auto-creates subdirs)."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.ohlcv_dir = self.data_dir / "ohlcv"
        self.mcap_dir = self.data_dir / "market_cap"
        self.mcap_daily_dir = self.mcap_dir / "mcap_daily"
        self.metadata_dir = self.data_dir / "metadata"

        for d in (self.ohlcv_dir, self.mcap_dir, self.mcap_daily_dir, self.metadata_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Atomic write helpers (the only place try/except is permitted)
    # ------------------------------------------------------------------

    def _atomic_write_csv(self, df: pd.DataFrame, path: Path) -> None:
        """Write `df` to CSV atomically.

        Strategy: write to `<path>.tmp`, then `os.replace(tmp, path)`.
        On any failure, attempt to clean up the .tmp file and re-raise.
        """
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            df.to_csv(tmp, index=False)
            os.replace(tmp, path)
        except Exception:
            # Cleanup: remove a half-written tmp file so the next run
            # doesn't see stale partial data.
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            raise

    def _atomic_write_json(self, payload: Dict, path: Path) -> None:
        """Same .tmp+replace pattern for JSON metadata files."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, path)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            raise

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------

    def _ohlcv_path(self, cg_id: str) -> Path:
        return self.ohlcv_dir / f"{cg_id}.csv"

    def read_ohlcv(self, cg_id: str) -> Optional[pd.DataFrame]:
        """Read OHLCV CSV for cg_id. Returns None if missing or empty."""
        path = self._ohlcv_path(cg_id)
        if not path.exists():
            return None
        # Guard against zero-byte file (no try/except: we use stat first).
        if path.stat().st_size == 0:
            return None
        df = pd.read_csv(path)
        if df.empty:
            return None
        # Ensure canonical column order if all present.
        existing = [c for c in OHLCV_COLUMNS if c in df.columns]
        return df[existing].copy()

    def write_ohlcv(self, cg_id: str, df: pd.DataFrame, source: str) -> None:
        """Atomic overwrite of `ohlcv/<cg_id>.csv` with the full dataframe.

        Required df columns: date, open, high, low, close, volume.
        A `source` column is added/overwritten using the supplied value.
        Dates are coerced to ISO YYYY-MM-DD strings.
        """
        out = df.copy()
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        out["source"] = source

        # Reorder/select canonical columns. Missing columns will raise via KeyError
        # which is appropriate — bad input should fail loud.
        out = out[OHLCV_COLUMNS]
        # Sort + dedupe by date before persisting.
        out = out.drop_duplicates(subset=["date"], keep="last").sort_values("date")

        self._atomic_write_csv(out, self._ohlcv_path(cg_id))

    def append_ohlcv(self, cg_id: str, new_rows: pd.DataFrame) -> int:
        """Append new rows to `ohlcv/<cg_id>.csv`, dedupe by date.

        Strategy: read existing -> concat -> drop_duplicates(subset=['date'])
        -> sort -> atomic write whole file. For 1095-row files this is fine.

        Returns the number of NEW rows actually persisted (i.e. rows whose
        date did not already exist in the file).
        """
        if new_rows is None or new_rows.empty:
            return 0

        incoming = new_rows.copy()
        incoming["date"] = pd.to_datetime(incoming["date"]).dt.strftime("%Y-%m-%d")
        # Ensure all canonical columns exist on incoming; fill source if absent.
        if "source" not in incoming.columns:
            incoming["source"] = ""
        for col in OHLCV_COLUMNS:
            if col not in incoming.columns:
                # Refuse silent fabrication of price/volume columns.
                if col in ("open", "high", "low", "close", "volume"):
                    raise KeyError(f"append_ohlcv: missing required column '{col}'")
                incoming[col] = ""
        incoming = incoming[OHLCV_COLUMNS]

        existing = self.read_ohlcv(cg_id)
        if existing is None or existing.empty:
            combined = incoming
            new_count = len(incoming)
        else:
            existing_dates = set(existing["date"].astype(str).tolist())
            new_count = int((~incoming["date"].astype(str).isin(existing_dates)).sum())
            combined = pd.concat([existing, incoming], ignore_index=True)

        combined = combined.drop_duplicates(subset=["date"], keep="last")
        combined = combined.sort_values("date").reset_index(drop=True)
        self._atomic_write_csv(combined, self._ohlcv_path(cg_id))
        return new_count

    def list_ohlcv_ids(self) -> List[str]:
        """Return sorted list of cg_ids present in `ohlcv/` (by filename)."""
        return sorted(
            p.stem
            for p in self.ohlcv_dir.glob("*.csv")
            if not p.name.endswith(".tmp")
        )

    # ------------------------------------------------------------------
    # P0-M: ohlcv/ backup snapshots (before run_full_initial_load
    # overwrites every file). Naming: ohlcv_backup_YYYYMMDD/. Kept count
    # comes from `BACKUP_KEEP` in config; older backups are deleted.
    # try/except is permitted here under the atomic-write helper carve-
    # out (option B in the hard rules): copytree/rmtree must not crash
    # the daily refresh on a stale file-handle or a missing-source case.
    # ------------------------------------------------------------------

    def snapshot_ohlcv_backup(self, today: Optional[_dt.date] = None) -> Optional[Path]:
        """Snapshot `ohlcv/` to `ohlcv_backup_YYYYMMDD/`.

        Returns the snapshot directory path on success (or if the existing
        backup is reused), else None when source ohlcv/ is missing or empty.
        Idempotent: if today's backup already exists it is left alone and
        returned as-is.
        """
        if today is None:
            today = _dt.date.today()
        iso = today.strftime("%Y%m%d")
        target = self.data_dir / f"ohlcv_backup_{iso}"

        if not self.ohlcv_dir.exists():
            return None
        # Avoid an empty backup when ohlcv/ has no CSVs.
        if not any(self.ohlcv_dir.glob("*.csv")):
            return None

        if target.exists():
            return target

        try:
            shutil.copytree(self.ohlcv_dir, target)
        except Exception:
            # On a failed copy, clean up the partial dir so the next run
            # is consistent. Re-raise to surface the original error.
            if target.exists():
                try:
                    shutil.rmtree(target)
                except Exception:
                    pass
            raise
        return target

    def prune_ohlcv_backups(self, keep: int) -> int:
        """Delete oldest `ohlcv_backup_*` dirs until only `keep` remain.

        Returns the number of directories removed.
        """
        if keep < 0:
            keep = 0
        all_backups = sorted(
            p for p in self.data_dir.glob("ohlcv_backup_*") if p.is_dir()
        )
        if len(all_backups) <= keep:
            return 0
        to_remove = all_backups[: len(all_backups) - keep]
        removed = 0
        for p in to_remove:
            try:
                shutil.rmtree(p)
                removed += 1
            except Exception:
                # Skip un-removable dirs (filesystem permission, etc.) but
                # keep going through the rest of the list.
                pass
        return removed

    # ------------------------------------------------------------------
    # Market cap
    # ------------------------------------------------------------------

    def write_top200_current(self, df: pd.DataFrame) -> None:
        """Atomic overwrite of `market_cap/top200_current.csv`.

        Caller is responsible for column shape; we just persist the dataframe.
        """
        self._atomic_write_csv(df.copy(), self.mcap_dir / TOP200_CURRENT_FILENAME)

    def read_top200_current(self) -> Optional[pd.DataFrame]:
        path = self.mcap_dir / TOP200_CURRENT_FILENAME
        if not path.exists() or path.stat().st_size == 0:
            return None
        df = pd.read_csv(path)
        if df.empty:
            return None
        return df

    def write_mcap_snapshot(self, date: _dt.date, df: pd.DataFrame) -> None:
        """Atomic overwrite of `market_cap/mcap_daily/YYYY-MM-DD.csv`.

        Accepts datetime.date OR a string that parses to ISO date.
        """
        if isinstance(date, _dt.datetime):
            iso = date.date().isoformat()
        elif isinstance(date, _dt.date):
            iso = date.isoformat()
        else:
            # String — coerce via pandas without try/except.
            iso = pd.to_datetime(str(date)).date().isoformat()

        path = self.mcap_daily_dir / f"{iso}.csv"
        self._atomic_write_csv(df.copy(), path)

    def list_mcap_snapshots(self) -> List[str]:
        """Return sorted list of ISO date strings present in mcap_daily/."""
        return sorted(
            p.stem
            for p in self.mcap_daily_dir.glob("*.csv")
            if not p.name.endswith(".tmp")
        )

    # ------------------------------------------------------------------
    # Scores history (P0-D): persisted daily snapshot of trend / reversal
    # scores per token. Append-only, deduped by (date, cg_id) keeping the
    # latest row. The 2y / 3y time-series percentile in data_service.py
    # reads from this file instead of recomputing from indicator means.
    # ------------------------------------------------------------------

    @property
    def _scores_history_path(self) -> Path:
        return self.mcap_dir / SCORES_HISTORY_FILENAME

    def read_scores_history(self) -> Optional[pd.DataFrame]:
        """Read the scores_history.csv file. Returns None when missing/empty."""
        path = self._scores_history_path
        if not path.exists() or path.stat().st_size == 0:
            return None
        df = pd.read_csv(path)
        if df.empty:
            return None
        # Coerce to expected column order. Missing optional columns are
        # tolerated (older snapshots before this file existed).
        for col in SCORES_HISTORY_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        return df[SCORES_HISTORY_COLUMNS].copy()

    def append_scores_history(self, date, df_scores: pd.DataFrame) -> int:
        """Append a daily snapshot to scores_history.csv (atomic write).

        Args:
            date:       datetime.date | str — the snapshot date.
            df_scores:  DataFrame with columns [cg_id, trend_score,
                        reversal_score, trend_cs_percentile,
                        reversal_cs_percentile]. Missing cols are filled NaN.

        Strategy: read existing -> drop any rows for the same date -> concat
        -> atomic write. Returns the number of new rows persisted today
        (0 if df_scores is empty).

        Dedupe is on (date, cg_id) keeping the **latest** write so a
        manual re-run during the day overwrites that day's snapshot
        without growing the file unboundedly.
        """
        if df_scores is None or df_scores.empty:
            return 0

        if isinstance(date, _dt.datetime):
            iso = date.date().isoformat()
        elif isinstance(date, _dt.date):
            iso = date.isoformat()
        else:
            iso = pd.to_datetime(str(date)).date().isoformat()

        incoming = df_scores.copy()
        incoming["date"] = iso
        for col in SCORES_HISTORY_COLUMNS:
            if col not in incoming.columns:
                incoming[col] = pd.NA
        incoming = incoming[SCORES_HISTORY_COLUMNS]

        existing = self.read_scores_history()
        if existing is None or existing.empty:
            combined = incoming
        else:
            # Drop any prior rows for this date (overwrite same-day snapshot).
            existing = existing[existing["date"].astype(str) != iso]
            combined = pd.concat([existing, incoming], ignore_index=True)

        combined = combined.drop_duplicates(
            subset=["date", "cg_id"], keep="last"
        )
        combined = combined.sort_values(["date", "cg_id"]).reset_index(drop=True)
        self._atomic_write_csv(combined, self._scores_history_path)
        return int(len(incoming))

    # ------------------------------------------------------------------
    # Metadata: last_update.json
    # ------------------------------------------------------------------

    @property
    def _last_update_path(self) -> Path:
        return self.metadata_dir / LAST_UPDATE_FILENAME

    def read_last_update(self) -> Dict:
        """Read last_update.json, returning {} if missing/empty."""
        path = self._last_update_path
        if not path.exists() or path.stat().st_size == 0:
            return {}
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def write_last_update(self, d: Dict) -> None:
        """Atomic write of last_update.json."""
        self._atomic_write_json(d, self._last_update_path)

    # ------------------------------------------------------------------
    # Metadata: data_integrity_log.json (convenience for validator output)
    # ------------------------------------------------------------------

    def write_integrity_log(self, payload: Dict) -> None:
        self._atomic_write_json(payload, self.metadata_dir / DATA_INTEGRITY_LOG_FILENAME)

    def read_integrity_log(self) -> Dict:
        path = self.metadata_dir / DATA_INTEGRITY_LOG_FILENAME
        if not path.exists() or path.stat().st_size == 0:
            return {}
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)
