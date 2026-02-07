# src/fetcher/etherscan.py
from __future__ import annotations

import os
import time
import requests
from typing import List, Dict, Any, Optional


ETHEREUM_MAINNET_CHAIN_ID = 1


class EtherscanFetcher:
    """
    Minimal tx list fetcher for Ethereum mainnet (Etherscan API V2).

    - Uses account/txlist endpoint
    - Supports time window filtering
    - Safe for MVP usage
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.etherscan.io/v2/api",
        chainid: int = ETHEREUM_MAINNET_CHAIN_ID,
        timeout: int = 20,
        sleep_sec: float = 0.2,
    ):
        self.api_key = api_key or os.getenv("ETHERSCAN_API_KEY", "")
        self.base_url = base_url
        self.chainid = chainid
        self.timeout = timeout
        self.sleep_sec = sleep_sec

        if not self.api_key:
            raise ValueError("Missing ETHERSCAN_API_KEY in environment variables.")

    def get_wallet_txs(
        self,
        wallet: str,
        t0: int,
        t1: int,
        only_from_wallet: bool = True,
        only_success: bool = True,
        sort: str = "asc",
        page: int = 1,
        offset: int = 1000,
        max_pages: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Fetch normal transactions (txlist) for a wallet within [t0, t1).

        Returns list of dicts:
          - hash
          - timestamp
          - from
          - to
          - is_error
        """

        wallet = wallet.lower()
        all_out: List[Dict[str, Any]] = []

        for p in range(page, page + max_pages):
            params = {
                "chainid": 1,          # ⭐ 必须：Etherscan V2
                "module": "account",
                "action": "txlist",
                "address": wallet,
                "startblock": 0,
                "endblock": 99999999,
                "page": p,
                "offset": offset,
                "sort": sort,
                "apikey": self.api_key,
            }

            r = requests.get(self.base_url, params=params, timeout=self.timeout)
            r.raise_for_status()
            payload = r.json()

            # ---------- 错误处理（V2 友好） ----------
            if payload.get("status") != "1":
                msg = payload.get("result") or payload.get("message")
                if msg == "No transactions found":
                    break
                raise RuntimeError(f"Etherscan API error: {msg}")

            txs = payload.get("result", [])
            if not txs:
                break

            for tx in txs:
                ts = int(tx.get("timeStamp", "0"))
                if ts >= t1:
                    continue
                if ts < t0:
                    # 已经早于窗口，可以提前结束（sort=asc）
                    return all_out

                if only_from_wallet and tx.get("from", "").lower() != wallet:
                    continue

                # txlist: isError == "0" 表示成功
                if only_success and tx.get("isError") != "0":
                    continue

                all_out.append({
                    "hash": tx.get("hash"),
                    "timestamp": ts,
                    "from": tx.get("from", "").lower(),
                    "to": tx.get("to", "").lower(),
                    "is_error": tx.get("isError"),
                })

            # MVP 级限速保护（非常重要）
            time.sleep(self.sleep_sec)

        return all_out
