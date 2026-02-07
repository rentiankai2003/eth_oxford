# scripts/replay_event.py
import sys
from pathlib import Path
import json

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.resolver.tx_count_resolver import TxCountResolver

if __name__ == "__main__":
    spec = json.load(open("config/market_spec.json", "r", encoding="utf-8"))
    resolver = TxCountResolver(spec)

    # 你填一个历史 to (UTC 秒)，或直接用当前时间 - 3600
    to = int(input("to unix seconds (UTC): ").strip())
    res = resolver.resolve(to)

    print(res)



'''
 $env:ETHERSCAN_API_KEY="QM2BH9YXXJYKS4DGXZP7PECCEQ8E8YSN4W"
>> echo $env:ETHERSCAN_API_KEY
>> python scripts/replay_event.py
'''