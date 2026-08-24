"""Isolate the ML scoring node: hammer /score directly, bypassing the switch.

If the end-to-end ceiling (~95 TPS) reproduces here, the bottleneck is the
Python inference node, not the switch's pessimistic ledger locks.
"""
import json, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib import request as urlrequest

URL = "http://127.0.0.1:8001/score"
BODY = json.dumps({
    "amount_inr": 500.0, "hour_of_day": 13, "is_weekend": 0,
    "transaction_type": "P2M", "merchant_category": "Grocery",
    "sender_age_group": "26-35", "receiver_age_group": "26-35",
    "sender_state": "Delhi", "sender_bank": "Axis", "receiver_bank": "SBI",
    "device_type": "Android", "network_type": "4G", "day_of_week": "Tuesday",
}).encode()


def one(_):
    t0 = time.perf_counter()
    req = urlrequest.Request(URL, data=BODY,
                             headers={"Content-Type": "application/json"})
    with urlrequest.urlopen(req, timeout=30) as r:
        r.read()
    return (time.perf_counter() - t0) * 1000


def pct(v, p):
    o = sorted(v); k = (len(o) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(o) - 1)
    return o[lo] + (o[hi] - o[lo]) * (k - lo)


print(f"{'conc':>5} {'tps':>8} {'mean':>8} {'p50':>8} {'p95':>8} {'p99':>8}")
for c in [1, 10, 25, 50, 100]:
    one(0)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=c) as pool:
        lat = list(pool.map(one, range(400)))
    wall = time.perf_counter() - t0
    print(f"{c:>5} {400/wall:>8.1f} {statistics.fmean(lat):>8.1f} "
          f"{pct(lat,50):>8.1f} {pct(lat,95):>8.1f} {pct(lat,99):>8.1f}")
