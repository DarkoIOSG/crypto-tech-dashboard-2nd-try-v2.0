"""Coin exclusion logic.

Reproduces notebook cell 2 (1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb)
verbatim. Removes stablecoins, wrapped/staked derivatives, RWA tokens, and other
items not appropriate for technical-indicator scoring.

Hard rule (A2): NO try/except anywhere in this file.
"""

from __future__ import annotations

from typing import Dict, List


# ---------------------------------------------------------------------------
# Verbatim from notebook cell 2 (lines 19-30 of that cell).
# DO NOT modify ordering or contents.
# ---------------------------------------------------------------------------

EXCLUDE_KEYWORDS: List[str] = [
    "usd", "usdt", "usdc", "busd", "dai", "tusd", "usdp", "gusd", "lusd", "fdusd",
    "usdd", "susd", "eusd", "wrapped", "wbtc", "weth", "renbtc", "staked", "stake",
]

EXCLUDE_IDS: List[str] = [
    "bridged-wrapped-ether-starkgate", "sbtc-2", "wrapped-zenbtc", "liquid-hype-yield",
    "compound-ether", "binance-peg-sol", "bitcoin-avalanche-bridged-btc-b", "binance-peg-dogecoin",
    "tbtc", "clbtc", "tether-gold", "rocket-pool-eth", "solv-btc", "pax-gold",
    "cgeth-hashkey", "frax-ether", "resolv-usr", "jupiter-perpetual", "gho", "stasis-eurs", "dola-usd", "blockchain-capital",
    "ousg", "mbg-by-multibank-group", "tradable-na-rent-financing-platform-sstn", "kinesis-gold", "kinesis-silver", "spiko-us-t-bills-money-market-fund",
    "onyc", "tradable-singapore-fintech-ssl-2", "vaneck-treasury-fund",
]


# ---------------------------------------------------------------------------
# Predicate (verbatim from notebook cell 2 lines 32-36)
# ---------------------------------------------------------------------------

def is_excluded(coin: Dict) -> bool:
    """Return True if coin matches the keyword or ID blacklist.

    Mirrors notebook cell 2 exactly:
        name = coin["name"].lower()
        symbol = coin["symbol"].lower()
        cid = coin["id"].lower()
        return (any(kw in name or kw in symbol for kw in exclude_keywords)
                or cid in exclude_ids)
    """
    name = coin["name"].lower()
    symbol = coin["symbol"].lower()
    cid = coin["id"].lower()
    return (
        any(kw in name or kw in symbol for kw in EXCLUDE_KEYWORDS)
        or cid in EXCLUDE_IDS
    )


def filter_coins(coins: List[Dict]) -> List[Dict]:
    """Convenience: return coins with excluded entries removed.

    Preserves input order. Does not mutate input.
    """
    return [c for c in coins if not is_excluded(c)]
