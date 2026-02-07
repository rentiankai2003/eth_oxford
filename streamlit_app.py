# streamlit_app.py
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.resolver.tx_count_resolver import TxCountResolver
from src.fetcher.etherscan import EtherscanFetcher


ROOT = Path(__file__).resolve().parent


def utc_dt_from_ts(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_spec(spec_path: Path) -> dict:
    return json.loads(spec_path.read_text(encoding="utf-8"))


@st.cache_resource(show_spinner=False)
def build_resolver(spec: dict) -> TxCountResolver:
    fetcher = EtherscanFetcher()
    return TxCountResolver(spec, fetcher=fetcher)


def main():
    st.set_page_config(page_title="Wallet Action Market — MVP", layout="wide")

    # =========================
    # Header
    # =========================
    st.title("Wallet Action Market — MVP (Tx Count Resolver)")
    st.caption(
        "Settlement rule: count(successful tx where from = wallet and block_time in [t0, t1)) ≥ 2 "
        "(default window: 10 minutes)"
    )
    st.info(
        "This is an MVP for a **behavior-based on-chain prediction market**. "
        "We define a verifiable wallet action (event) and settle it using public on-chain data.\n\n"
        "**In this demo:** You place YES/NO orders like Polymarket, then click **Resolve** to settle "
        "based on Etherscan-verified transaction data."
    )

    # =========================
    # Sidebar: Spec
    # =========================
    st.sidebar.header("Configuration / Spec")
    default_spec_path = ROOT / "config" / "market_spec.json"
    spec_path = st.sidebar.text_input("Spec file path", value=str(default_spec_path))

    if not os.getenv("ETHERSCAN_API_KEY"):
        st.sidebar.error("Missing environment variable: ETHERSCAN_API_KEY")
        st.sidebar.code("export ETHERSCAN_API_KEY=xxxx")
    else:
        st.sidebar.success("ETHERSCAN_API_KEY detected")

    try:
        spec = load_spec(Path(spec_path))
    except Exception as e:
        st.error(f"Failed to load spec: {e}")
        st.stop()

    # Spec summary
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Market ID", spec.get("market_id", "N/A"))
    col_b.metric("Event", spec.get("event", {}).get("name", "N/A"))
    col_c.metric("Window (seconds)", spec.get("window", {}).get("length_seconds", "N/A"))

    with st.expander("View full market_spec.json (read-only)", expanded=False):
        st.json(spec)

    # =========================
    # Inputs: Time + Wallet
    # =========================
    st.subheader("Inputs (Time & Wallet)")

    # Time selection (lookback)
    st.markdown("### Time Selection")
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    st.write(f"**Current UTC time:** {utc_dt_from_ts(now_ts)}")

    lookback_minutes = st.slider(
        "Lookback from now (minutes)",
        min_value=1,
        max_value=180,
        value=60,
        step=5,
        help="Start the window this many minutes BEFORE current UTC time."
    )

    t0 = now_ts - lookback_minutes * 60
    window_seconds_preview = int(spec.get("window", {}).get("length_seconds", 600))
    t1_preview = int(t0) + window_seconds_preview

    c1, c2, c3 = st.columns(3)
    c1.metric("t0 (UTC)", utc_dt_from_ts(t0))
    c2.metric("t0 (Unix)", t0)
    c3.metric("t1 (UTC)", utc_dt_from_ts(t1_preview))

    # Wallet selection
    st.markdown("### Wallet Selection")
    st.caption("We resolve transactions **sent from this wallet** within the settlement window.")

    wallet_override = st.text_input(
        "Wallet address (leave empty to use spec.wallet.address)",
        value="",
        help="For testing only. The resolver still executes the spec-defined rule."
    ).strip()

    effective_wallet = wallet_override or spec.get("wallet", {}).get("address", "")
    st.code(f"Effective wallet: {effective_wallet}")

    # =========================
    # Market UI (Polymarket-style demo)
    # =========================
    st.divider()
    st.subheader("Market UI (Polymarket-style demo)")

    with st.expander("What is being traded here? (Definitions)", expanded=True):
        st.markdown(
            """
**Contract type:** Binary event contract (YES/NO)

**Payoff:**
- A **YES share** pays **$1** if the event resolves **YES**, otherwise **$0**.
- A **NO share** pays **$1** if the event resolves **NO**, otherwise **$0**.

**Price interpretation:**
- YES price (e.g., $0.63) ≈ implied probability (≈ 63% chance of YES).
- NO price ≈ 1 − YES price.

**Demo limitations:**
- The “price slider” is a **demo control** (no AMM / no real orderbook / no matching).
- Orders are stored **locally in this Streamlit session** (not on-chain, not shared).

**Settlement source of truth:**
- On-chain data via Etherscan within **[t0, t1)**.
            """
        )

    # init session state
    if "yes_price" not in st.session_state:
        st.session_state.yes_price = 0.50
    if "no_price" not in st.session_state:
        st.session_state.no_price = 0.50
    if "orders" not in st.session_state:
        st.session_state.orders = []
    st.session_state.setdefault("last_settlement", None)

    # market header
    m1, m2, m3 = st.columns([1.4, 1, 1])
    with m1:
        st.markdown(f"**Market:** {spec.get('event', {}).get('name', 'N/A')}")
        st.caption("A share pays $1 if the event resolves YES, else $0.")
    with m2:
        st.metric("YES price", f"${st.session_state.yes_price:.2f}")
    with m3:
        st.metric("NO price", f"${st.session_state.no_price:.2f}")

    st.caption(f"Settlement window: {utc_dt_from_ts(int(t0))} → {utc_dt_from_ts(int(t1_preview))}")

    # price controls
    with st.expander("Price controls (demo only)", expanded=False):
        p = st.slider("Implied probability (YES)", 0.01, 0.99, float(st.session_state.yes_price), 0.01)
        st.session_state.yes_price = round(float(p), 2)
        st.session_state.no_price = round(1 - float(st.session_state.yes_price), 2)
        st.info("Demo slider only. Real markets move prices via trades.")

    # trade panel
    trade_left, trade_right = st.columns([1.2, 1])

    with trade_left:
        st.markdown("### Place an order (demo)")
        side = st.radio("Side", ["YES", "NO"], horizontal=True)
        shares = st.number_input("Shares", min_value=1, value=10, step=1)
        price = st.number_input(
            "Limit price ($)",
            min_value=0.01,
            max_value=0.99,
            value=float(st.session_state.yes_price if side == "YES" else st.session_state.no_price),
            step=0.01,
            format="%.2f"
        )

        cta1, cta2 = st.columns(2)
        with cta1:
            if st.button("Buy", use_container_width=True):
                st.session_state.orders.append({
                    "action": "BUY",
                    "side": side,
                    "shares": int(shares),
                    "price": float(price),
                    "created_at_utc": utc_dt_from_ts(int(datetime.now(tz=timezone.utc).timestamp())),
                    "wallet": effective_wallet,
                    "t0": int(t0),
                    "t1": int(t1_preview),
                    "status": "OPEN",
                })
                st.success("Order created (demo).")
        with cta2:
            if st.button("Clear orders", use_container_width=True):
                st.session_state.orders = []
                st.warning("Orders cleared.")

    with trade_right:
        st.markdown("### Open orders")
        if not st.session_state.orders:
            st.info("No open orders yet.")
        else:
            df_orders = pd.DataFrame(st.session_state.orders)
            st.dataframe(
                df_orders[["created_at_utc", "action", "side", "shares", "price", "status"]],
                use_container_width=True
            )

    st.markdown("### Settlement (demo)")
    st.caption("When you click Resolve, we fetch transactions from Etherscan and settle based on the spec.")

    # =========================
    # Resolve button (AFTER user sees market + places orders)
    # =========================
    r1, r2 = st.columns([1, 2])
    with r1:
        run = st.button("Resolve", type="primary", use_container_width=True)
    with r2:
        st.caption(
            "Resolve fetches transactions from Etherscan for the selected wallet and time window, "
            "then computes the outcome strictly according to the spec."
        )

    if not run:
        st.stop()

    # =========================
    # Resolve execution
    # =========================
    try:
        resolver = build_resolver(spec)
    except Exception as e:
        st.error(f"Failed to initialize resolver: {e}")
        st.stop()

    # apply wallet override by cloning spec (do not mutate original)
    if wallet_override:
        spec2 = json.loads(json.dumps(spec))
        spec2["wallet"]["address"] = wallet_override
        try:
            resolver = build_resolver(spec2)
        except Exception as e:
            st.error(f"Failed to initialize resolver with wallet override: {e}")
            st.stop()

    window_seconds = int(resolver.window_seconds)
    t1 = int(t0) + window_seconds

    with st.spinner("Fetching transactions from Etherscan and resolving event..."):
        res = resolver.resolve(int(t0), int(t1))

    # =========================
    # Output
    # =========================
    st.success(
        f"Outcome = {res.outcome} "
        f"(tx_count = {res.tx_count}, "
        f"window {utc_dt_from_ts(res.t0)} → {utc_dt_from_ts(res.t1)})"
    )

    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("### Resolve Result")
        st.json({
            "event": res.event,
            "wallet": res.wallet,
            "t0": res.t0,
            "t1": res.t1,
            "tx_count": res.tx_count,
            "outcome": res.outcome,
            "evidence": res.evidence,
            "meta": res.meta,
        })

    with right:
        st.markdown("### Evidence (Transaction Hashes)")
        if res.evidence:
            for h in res.evidence:
                st.code(h)
        else:
            st.info("No transactions matched the filter in this window.")

        st.markdown("### Rule Confirmation (from spec)")
        st.write(spec["event"]["definition"])
        st.caption("Note: The resolver does not modify rules; it only executes the spec.")

    # =========================
    # Transaction details
    # =========================
    st.divider()
    st.markdown("## Transaction Details (within window)")

    show_detail = st.checkbox("Show transaction details (may be slow)", value=True)
    if show_detail:
        try:
            fetcher = EtherscanFetcher()
            txs = fetcher.get_wallet_txs(
                wallet=res.wallet,
                t0=res.t0,
                t1=res.t1,
                only_from_wallet=True,
                only_success=True,
                sort="asc",
                page=1,
                offset=1000
            )
            if not txs:
                st.info("No transactions in this window.")
            else:
                df = pd.DataFrame(txs)
                df["time_utc"] = df["timestamp"].apply(utc_dt_from_ts)
                st.dataframe(
                    df[["time_utc", "timestamp", "hash", "from", "to", "is_error"]],
                    use_container_width=True
                )
        except Exception as e:
            st.warning(f"Failed to fetch transaction details: {e}")

    # =========================
    # Demo settlement PnL
    # =========================
    st.markdown("## Market Settlement Result (demo PnL)")

    with st.expander("How is demo PnL calculated?", expanded=False):
        st.markdown(
            """
This is **demo accounting** (not real trading execution).

For each OPEN order:
- If you bought **YES** at price *p*, your payoff is *payout* (1 if YES, else 0).
  - **PnL = (payout − p) × shares**
- If you bought **NO** at price *p*, payoff is *(1 − payout)*.
  - **PnL = ((1 − payout) − p) × shares**

No fees, no slippage, no matching, no partial fills.
            """
        )

    resolved_yes = (res.outcome == "YES")
    payout = 1.0 if resolved_yes else 0.0

    if st.session_state.get("orders"):
        rows = []
        for o in st.session_state.orders:
            if o.get("status") != "OPEN":
                continue

            if o["side"] == "YES":
                realized = (payout - o["price"]) * o["shares"]
                side_payout = payout
            else:
                realized = ((1.0 - payout) - o["price"]) * o["shares"]
                side_payout = (1.0 - payout)

            rows.append({
                "side": o["side"],
                "shares": o["shares"],
                "entry_price": o["price"],
                "payout": side_payout,
                "pnl_$": round(realized, 4),
            })

        if rows:
            df_pnl = pd.DataFrame(rows)
            st.dataframe(df_pnl, use_container_width=True)
            st.metric("Total PnL ($, demo)", round(df_pnl["pnl_$"].sum(), 4))
        else:
            st.info("No OPEN orders to settle.")
    else:
        st.info("No orders placed. Use the Market UI above to create demo orders.")


if __name__ == "__main__":
    main()
