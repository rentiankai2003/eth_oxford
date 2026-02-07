# src/utils/time.py
import time


def ensure_utc_int(x) -> int:
    x = int(x)
    if x <= 0:
        raise ValueError("timestamp must be positive unix seconds")
    return x


def now_utc_int() -> int:
    return int(time.time())
