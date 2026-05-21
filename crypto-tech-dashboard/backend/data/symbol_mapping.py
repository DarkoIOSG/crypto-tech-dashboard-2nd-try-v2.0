"""CoinGecko-ID <-> exchange-pair symbol mapping with auto-discovery.

Per PLAN section 3.3 and 3.4:
- For each cg_id, try multiple naming conventions across the 4 exchanges
  (Binance -> OKX -> Bybit -> Gate.io priority).
- Persist results to local_data/metadata/symbol_map.json.
- Honour manual overrides from local_data/metadata/symbol_map_manual.json
  when present (manual takes precedence over auto).

Hard rule (A2): NO try/except anywhere in this file.

Contract for A1 (Fetcher Author):
    from backend.data.symbol_mapping import SymbolMapper
    mapper = SymbolMapper(metadata_dir, exchange_client)
    mapper.get_symbol(cg_id, exchange) -> str | None     # CCXT "BTC/USDT" or None
    mapper.discover(cg_ids: list[str]) -> dict           # per-cg_id per-exchange map
    mapper.save() / mapper.load()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional


# Priority order from PLAN section 3.1 ("EXCHANGE_PRIORITY").
# R8-1B.1: import from config so the mapper stays in lock-step with the
# 8-exchange waterfall. The original hard-coded list left BTC/ETH unmapped
# on Coinbase/Kraken/KuCoin/Bitstamp; today every entry is consulted.
from backend.config import EXCHANGE_PRIORITY  # noqa: E402  (intentional after constants above)

# Quote-symbol candidates tried in order. PLAN section 3.1 prefers USDT.
# USD and BUSD are fallbacks; USDC is intentionally skipped.
QUOTE_CANDIDATES: List[str] = ["USDT", "USD", "BUSD"]

SYMBOL_MAP_FILENAME = "symbol_map.json"
MANUAL_OVERRIDE_FILENAME = "symbol_map_manual.json"


class SymbolMapper:
    """Per-(cg_id, exchange) symbol mapper with persistence."""

    def __init__(self, metadata_dir, exchange_client):
        """
        Args:
            metadata_dir: Path-like directory holding symbol_map.json and
                (optionally) symbol_map_manual.json.
            exchange_client: An object exposing `.exchanges`, a dict of
                {exchange_name: ccxt_exchange_instance}. The caller is
                expected to have invoked `load_markets()` on each instance
                before discovery, so that `exchange.markets` is populated.
        """
        self.metadata_dir = Path(metadata_dir)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.exchange_client = exchange_client

        # Auto-discovered map. Shape:
        #   {cg_id: {"binance": "BTC/USDT" | None, "okx": ..., ...}}
        self.map: Dict[str, Dict[str, Optional[str]]] = {}

        # Manual override map (same shape; loaded from disk if file exists).
        self.manual: Dict[str, Dict[str, Optional[str]]] = {}

        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @property
    def _map_path(self) -> Path:
        return self.metadata_dir / SYMBOL_MAP_FILENAME

    @property
    def _manual_path(self) -> Path:
        return self.metadata_dir / MANUAL_OVERRIDE_FILENAME

    def load(self) -> None:
        """Load auto map and (if present) manual overrides from disk.

        Uses `Path.exists()` plus `json.loads(...)` directly — no try/except.
        """
        if self._map_path.exists():
            raw = self._map_path.read_text(encoding="utf-8")
            if raw.strip():
                self.map = json.loads(raw)
            else:
                self.map = {}
        else:
            self.map = {}

        if self._manual_path.exists():
            raw_m = self._manual_path.read_text(encoding="utf-8")
            if raw_m.strip():
                self.manual = json.loads(raw_m)
            else:
                self.manual = {}
        else:
            self.manual = {}

    def save(self) -> None:
        """Persist the auto map to symbol_map.json (pretty-printed)."""
        payload = json.dumps(self.map, indent=2, sort_keys=True, ensure_ascii=False)
        # Simple atomic write: tmp + replace. No try/except needed here
        # (file I/O atomicity for OHLCV lives in local_store.py only).
        tmp = self._map_path.with_suffix(self._map_path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._map_path)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_symbol(self, cg_id: str, exchange: str) -> Optional[str]:
        """Return CCXT symbol (e.g. 'BTC/USDT') for cg_id on exchange, else None.

        Manual override (if defined) takes precedence over auto-discovered.
        """
        manual_entry = self.manual.get(cg_id)
        if manual_entry is not None and exchange in manual_entry:
            return manual_entry[exchange]

        auto_entry = self.map.get(cg_id)
        if auto_entry is None:
            return None
        return auto_entry.get(exchange)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _candidate_symbols(self, base_symbol: str) -> List[str]:
        """Generate CCXT candidate symbols for a given base ticker."""
        base = base_symbol.upper()
        return [f"{base}/{quote}" for quote in QUOTE_CANDIDATES]

    def _markets_for(self, exchange_name: str) -> Dict[str, Dict]:
        """Return the markets dict for the named exchange, or {} if unknown.

        Assumes the caller has already invoked `load_markets()` upstream.
        We do not call it here (no try/except policy and to keep discovery
        a pure lookup).
        """
        exchange = self.exchange_client.exchanges.get(exchange_name)
        if exchange is None:
            return {}
        markets = getattr(exchange, "markets", None)
        if not markets:
            return {}
        return markets

    def discover(self, coins: Iterable) -> Dict[str, Dict[str, Optional[str]]]:
        """Build per-(cg_id, exchange) mapping for the given coins.

        Args:
            coins: iterable of either coin dicts (each having keys 'id' and
                'symbol' as returned by CoinGecko) OR plain cg_id strings.
                When strings are passed, the cg_id is also used as the
                base ticker — which only works for trivial cases — so prefer
                passing dicts.

        Returns the updated `self.map` (and also persists it to disk).
        """
        for coin in coins:
            if isinstance(coin, dict):
                cg_id = coin["id"]
                base = coin.get("symbol") or cg_id
            else:
                cg_id = coin
                base = coin

            per_exchange: Dict[str, Optional[str]] = {}
            for ex_name in EXCHANGE_PRIORITY:
                per_exchange[ex_name] = self._discover_single(ex_name, base)

            self.map[cg_id] = per_exchange

        self.save()
        return self.map

    def _discover_single(self, exchange_name: str, base_symbol: str) -> Optional[str]:
        """Try candidate quote symbols against `exchange.markets` and return first hit."""
        markets = self._markets_for(exchange_name)
        if not markets:
            return None
        for candidate in self._candidate_symbols(base_symbol):
            if candidate in markets:
                return candidate
        return None

    # ------------------------------------------------------------------
    # Introspection helpers (used by fetcher/UI status pages)
    # ------------------------------------------------------------------

    def best_exchange(self, cg_id: str) -> Optional[str]:
        """Return the highest-priority exchange that has a symbol for cg_id."""
        for ex_name in EXCHANGE_PRIORITY:
            sym = self.get_symbol(cg_id, ex_name)
            if sym:
                return ex_name
        return None

    def coverage_summary(self) -> Dict[str, int]:
        """Return {exchange_name: count_of_cg_ids_with_a_symbol}."""
        summary: Dict[str, int] = {ex: 0 for ex in EXCHANGE_PRIORITY}
        for cg_id, per_exchange in self.map.items():
            for ex_name in EXCHANGE_PRIORITY:
                if per_exchange.get(ex_name):
                    summary[ex_name] += 1
        return summary
