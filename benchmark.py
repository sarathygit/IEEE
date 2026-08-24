"""
FinGuard-AI :: Concurrency benchmark for the inline interception path.

Motivation
----------
The sub-50 ms design budget was originally measured single-request. The switch
holds PESSIMISTIC_WRITE locks on both ledger rows across the synchronous ML
scoring hop, so throughput and tail latency depend critically on whether
concurrent payments contend for the same account row. This harness measures
both regimes:

  * UNCONTENDED - every virtual user pays from a distinct account. Locks never
    collide; latency reflects pure pipeline cost under CPU/IO load.
  * CONTENDED   - every virtual user pays from ONE shared account. All requests
    serialize on that single row lock, each waiting for the previous scoring
    round-trip to complete. This is the architectural worst case.

Requires the switch (:8081) started with LOAD_POOL_SIZE>=concurrency and the
ML core (:8001) running.

Usage:
    python benchmark.py --levels 1,10,25,50,100 --requests-per-level 400
"""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib import request as urlrequest
from urllib import error as urlerror

SWITCH = "http://127.0.0.1:8081/api/v1/upi/pay"
MERCHANT = "grocery@fgpay"


def post_payment(payer_vpa: str, amount: float = 5.0) -> tuple[int, float]:
    """Fire one payment; return (http_status, wall_ms). Small amounts and
    ordinary context keep the anomaly score low so the ledger path (not the
    fraud path) is what gets measured."""
    payload = json.dumps({
        "payerVpa": payer_vpa,
        "payeeVpa": MERCHANT,
        "amountInr": amount,
        "mpin": "1234",
        "transactionType": "P2M",
        "merchantCategory": "Grocery",
        "deviceType": "Android",
        "networkType": "4G",
        "deviceSignature": "bench-sig",
        "geoLocationHash": "bench-geo",
    }).encode()

    req = urlrequest.Request(SWITCH, data=payload,
                             headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            status = resp.status
            resp.read()
    except urlerror.HTTPError as e:
        status = e.code
        e.read()
    except Exception:
        status = -1
    return status, (time.perf_counter() - t0) * 1000


def percentile(values, p):
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def run_level(concurrency: int, total_requests: int, contended: bool):
    """Drive `total_requests` payments through `concurrency` parallel workers."""
    if contended:
        payers = ["load01@fgbank"] * total_requests
    else:
        payers = [f"load{(i % concurrency) + 1:02d}@fgbank"
                  for i in range(total_requests)]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(post_payment, payers))
    wall_s = time.perf_counter() - t0

    oks = [ms for status, ms in results if status == 200]
    non200 = {}
    for status, _ in results:
        if status != 200:
            non200[status] = non200.get(status, 0) + 1

    return {
        "concurrency": concurrency,
        "mode": "contended" if contended else "uncontended",
        "requests": total_requests,
        "successful": len(oks),
        "non_200": non200,
        "throughput_tps": round(len(oks) / wall_s, 1) if wall_s else 0.0,
        "mean_ms": round(statistics.fmean(oks), 1) if oks else None,
        "p50_ms": round(percentile(oks, 50), 1) if oks else None,
        "p95_ms": round(percentile(oks, 95), 1) if oks else None,
        "p99_ms": round(percentile(oks, 99), 1) if oks else None,
        "max_ms": round(max(oks), 1) if oks else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="1,10,25,50,100")
    ap.add_argument("--requests-per-level", type=int, default=400)
    ap.add_argument("--output", default="benchmark_results.json")
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",")]
    all_results = []

    for contended in (False, True):
        label = "CONTENDED (single account)" if contended else "UNCONTENDED (distinct accounts)"
        print(f"\n=== {label} ===")
        print(f"{'conc':>5} {'tps':>8} {'mean':>8} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}  errors")
        for c in levels:
            # warm the path so JIT/connection setup isn't charged to the run
            post_payment("load01@fgbank")
            r = run_level(c, args.requests_per_level, contended)
            all_results.append(r)
            print(f"{r['concurrency']:>5} {r['throughput_tps']:>8} "
                  f"{r['mean_ms']:>8} {r['p50_ms']:>8} {r['p95_ms']:>8} "
                  f"{r['p99_ms']:>8} {r['max_ms']:>8}  {r['non_200'] or '-'}")
            time.sleep(1)

    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nWritten to {args.output}")


if __name__ == "__main__":
    main()
