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
    # 由 EtherscanFetcher 读取环境变量 ETHERSCAN_API_KEY（缺失会抛错）:contentReference[oaicite:3]{index=3}
    fetcher = EtherscanFetcher()
    return TxCountResolver(spec, fetcher=fetcher)


def main():
    st.set_page_config(page_title="Wallet Action Market — MVP", layout="wide")

    st.title("Wallet Action Market — MVP（Tx Count Resolver）")
    st.caption(
        "结算规则：count(success tx where from=wallet and block_time in [t0,t1)) >= 2（窗口默认 10 分钟）"
    )

    # ---- Sidebar: Spec selection / override ----
    st.sidebar.header("配置 / Spec")
    default_spec_path = ROOT / "config" / "market_spec.json"
    spec_path = st.sidebar.text_input("Spec 路径", value=str(default_spec_path))

    if not os.getenv("ETHERSCAN_API_KEY"):
        st.sidebar.error("环境变量缺失：ETHERSCAN_API_KEY（EtherscanFetcher 需要）")
        st.sidebar.code("export ETHERSCAN_API_KEY=xxxx")
    else:
        st.sidebar.success("已检测到 ETHERSCAN_API_KEY")

    try:
        spec = load_spec(Path(spec_path))
    except Exception as e:
        st.error(f"无法读取 spec：{e}")
        st.stop()

    # 展示当前 spec 关键信息（只读）
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("market_id", spec.get("market_id", "N/A"))
    col_b.metric("event", spec.get("event", {}).get("name", "N/A"))
    col_c.metric("window_seconds", spec.get("window", {}).get("length_seconds", "N/A"))

    with st.expander("查看完整 market_spec.json（只读）", expanded=False):
        st.json(spec)

    # ---- Main inputs: t0 ----
    st.subheader("运行一次结算（Resolve）")

    # 默认给一个“当前时间 - 1 小时”，对齐 scripts/replay_event.py 习惯 :contentReference[oaicite:4]{index=4}
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    default_t0 = now_ts - 3600

    c1, c2 = st.columns([2, 1])
    t0 = c1.number_input(
        "t0（UTC unix seconds）",
        min_value=1,
        value=int(default_t0),
        step=60,
        help="窗口为 [t0, t0+window_seconds)。"
    )
    c2.write("t0 可读时间：")
    c2.info(utc_dt_from_ts(int(t0)))

    # 允许用户临时覆盖钱包（不写回 spec，仅用于本次预览）
    st.markdown("### 可选：本次预览覆盖钱包地址（不修改 spec 文件）")
    wallet_override = st.text_input(
        "wallet override（留空=使用 spec.wallet.address）",
        value="",
        help="只用于前端测试，resolver 的规则仍然来自 spec。"
    ).strip()

    run = st.button("Resolve（结算）", type="primary")

    if not run:
        st.stop()

    # ---- Resolve ----
    try:
        resolver = build_resolver(spec)
    except Exception as e:
        st.error(f"Resolver 初始化失败：{e}")
        st.stop()

    # 如果用户覆盖钱包：做一个“浅拷贝 spec”给 resolver（不污染原 spec）
    if wallet_override:
        spec2 = json.loads(json.dumps(spec))
        spec2["wallet"]["address"] = wallet_override
        try:
            resolver = build_resolver(spec2)  # cache 会按入参 hash；spec2 不同则新建
        except Exception as e:
            st.error(f"使用 wallet override 初始化失败：{e}")
            st.stop()

    window_seconds = int(resolver.window_seconds)
    t1 = int(t0) + window_seconds

    with st.spinner("正在从 Etherscan 拉取交易并结算..."):
        res = resolver.resolve(int(t0), int(t1))

    # ---- Output ----
    st.success(f"Outcome = {res.outcome}（tx_count={res.tx_count}，窗口 {utc_dt_from_ts(res.t0)} → {utc_dt_from_ts(res.t1)}）")

    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("### 结算结果（ResolveResult）")
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
        st.markdown("### 证据（Tx Hashes）")
        if res.evidence:
            for h in res.evidence:
                st.code(h)
        else:
            st.info("该窗口内没有符合过滤条件的交易。")

        st.markdown("### 规则确认（来自 spec）")
        st.write(spec["event"]["definition"])
        st.caption("注意：resolver 不会改规则，只会执行 spec。")

    # ---- Optional: fetch full tx list for the window and show table ----
    st.divider()
    st.markdown("## 明细（窗口内交易列表）")

    show_detail = st.checkbox("显示窗口内交易明细（可能较慢）", value=True)
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
                st.info("窗口内无交易。")
            else:
                df = pd.DataFrame(txs)
                # 方便阅读：加一列可读时间
                df["time_utc"] = df["timestamp"].apply(utc_dt_from_ts)
                st.dataframe(df[["time_utc", "timestamp", "hash", "from", "to", "is_error"]], use_container_width=True)
        except Exception as e:
            st.warning(f"拉取明细失败：{e}")


if __name__ == "__main__":
    main()
