# src/resolver/tx_count_resolver.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from src.fetcher.etherscan import EtherscanFetcher
from src.utils.time import ensure_utc_int, now_utc_int


@dataclass
class ResolveResult:
    event: str
    wallet: str
    t0: int
    t1: int
    tx_count: int
    outcome: str                 # "YES" or "NO"
    evidence: List[str]          # tx_hashes (at least the ones counted)
    meta: Dict[str, Any]         # debug info, data source, warnings


class TxCountResolver:
    """
    Executes market_spec.json rules for:
      - event: TX_COUNT_GE_2
      - definition: count(success tx where from=wallet and block_time in [t0,t1)) >= 2

    IMPORTANT: This resolver MUST NOT change rules. It only reads spec and applies it.
    """

    def __init__(self, spec: Dict[str, Any], fetcher: Optional[EtherscanFetcher] = None):
        self.spec = spec

        # Extract immutable rules from spec (do not invent rules)
        self.event_name = spec["event"]["name"]
        self.wallet = spec["wallet"]["address"].lower()
        self.window_seconds = int(spec["window"]["length_seconds"])
        self.interval = spec["window"]["interval"]  # expected "[t0,t1)"

        # For MVP: only supports "[t0,t1)" interval (freeze it in spec)
        if self.interval != "[t0,t1)":
            raise ValueError(f"Unsupported interval: {self.interval}. Expected [t0,t1).")

        # Threshold rule for this resolver (still derived from the event name in spec)
        # Keeping it explicit to avoid hidden assumptions.
        if self.event_name != "TX_COUNT_GE_2":
            raise ValueError(f"TxCountResolver only supports event TX_COUNT_GE_2, got {self.event_name}")
        self.threshold = 2

        self.fetcher = fetcher or EtherscanFetcher()

    def resolve(self, t0: int, t1: Optional[int] = None) -> ResolveResult:
        """
        Resolve the event for [t0, t1). If t1 not provided, use t0 + window_seconds.

        t0/t1 must be UTC unix timestamps (seconds).
        """
        t0 = ensure_utc_int(t0)
        if t1 is None:
            t1 = t0 + self.window_seconds
        t1 = ensure_utc_int(t1)

        # Fetch transactions for this wallet in [t0, t1)
        txs = self.fetcher.get_wallet_txs(
            wallet=self.wallet,
            t0=t0,
            t1=t1,
            only_from_wallet=True,     # aligns with spec "from=wallet"
            only_success=True          # aligns with spec "success tx"
        )

        tx_hashes = [tx["hash"] for tx in txs]
        tx_count = len(txs)

        outcome = "YES" if tx_count >= self.threshold else "NO"

        meta = {
            "data_source": "etherscan_api",
            "resolved_at": now_utc_int(),
            "filters": {
                "only_from_wallet": True,
                "only_success": True,
                "interval": "[t0,t1)"
            }
        }

        return ResolveResult(
            event=self.event_name,
            wallet=self.wallet,
            t0=t0,
            t1=t1,
            tx_count=tx_count,
            outcome=outcome,
            evidence=tx_hashes[: max(self.threshold, 5)],  # keep it small but useful
            meta=meta
        )
