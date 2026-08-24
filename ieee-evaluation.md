# FinGuard-AI / RT-IIPF — Experimental Evaluation Package

Generated from `ml-service/evaluate.py` (seed 42, fully reproducible).
Raw machine-readable results: `ml-service/evaluation_results.json`.

**Integrity note:** every number in this document is a real measured output of
the evaluation script run against the actual trained pipeline on 2026-08-03.
Nothing is estimated or synthesized except the injected fraud vectors
themselves, which is the documented methodology.

---

## PART 1 — CAMERA-READY RESULT TABLES

### Table I. Synthetic fraud archetypes and detection at the production operating point (threshold τ = 0.85)

| Archetype | Definition | n | Mean anomaly score | Recall @ τ=0.85 |
|---|---|---|---|---|
| A — Off-hour high-value drain | ₹25K–60K, 01:00–04:00, P2P, web origin | 100 | 0.781 | 0.26 |
| B — Velocity spike *(negative control)* | ₹2K–6K, business hours, Android/4G; attack exists only in aggregate | 100 | 0.350 | **0.00** |
| C — Category anomaly | ₹50K–100K under Grocery (P2M), daytime | 100 | 0.567 | 0.07 |
| D — Context anomaly | ₹2K–9K, 00:00–04:00, Web/WiFi, P2P | 100 | 0.799 | 0.26 |
| — Clean held-out traffic | 50,000 genuine transactions | 50,000 | — | FPR = 0.0086 |

### Table II. Overall detection metrics, production configuration (Isolation Forest, 13 features, τ = 0.85)

| Metric | Value |
|---|---|
| Precision | 0.121 |
| Recall (TPR) | 0.148 |
| F1-score | 0.133 |
| False-positive rate | 0.0086 |
| ROC-AUC | 0.723 |

### Table III. Ablation of enrichment layers (same injected set; each layer independently trained and calibrated)

| Layer | Raw features | ROC-AUC | Recall @ τ | FPR @ τ | Score separation (synth − clean) | Recall A | Recall B | Recall C | Recall D |
|---|---|---|---|---|---|---|---|---|---|
| L1 — form inputs only | 3 | **0.860** | 0.010 | 0.0055 | 0.322 | 0.04 | 0.00 | 0.00 | **0.00** |
| L2 — + client telemetry | 5 | 0.747 | **0.228** | 0.0096 | 0.256 | **0.46** | 0.00 | 0.05 | **0.40** |
| L3 — + server enrichment | 13 | 0.723 | 0.148 | 0.0086 | 0.164 | 0.26 | 0.00 | 0.07 | 0.26 |

### Table IV. Baseline comparison (score-based detectors thresholded at an equal 1% FPR budget)

| Detector | ROC-AUC | Recall @ 1% FPR | Precision | F1 | Notes |
|---|---|---|---|---|---|
| Static rules | — | 0.658 | 0.305 | 0.417 | amount>p99 ∨ (amount>p95 ∧ hour≤5); FPR 1.2% |
| Local Outlier Factor | **0.896** | **0.745** | **0.373** | **0.497** | k=20, novelty mode, 40K train subsample |
| One-Class SVM | 0.783 | 0.675 | 0.351 | 0.462 | RBF, ν=0.002, 15K train subsample |
| Isolation Forest (deployed) | 0.723 | 0.163 | — | — | 200 trees; production τ=0.85 gives R=0.148 |

### Table V. Measured system latency (local deployment, Apple Silicon, 8 cores)

| Path | Latency |
|---|---|
| ML inference hop (warm, incl. HTTP) | 9–15 ms |
| End-to-end switch processing (auth → lock → score → verdict → commit/rollback) | 11–12 ms mean, p99 14 ms (single client) |
| Model bundle load at service startup (off hot path) | ~1 s |

### Table VI. End-to-end concurrency: contended vs. uncontended ledger access (400 requests per level)

| Concurrency | Uncontended TPS | Uncontended p50 / p95 (ms) | Contended TPS | Contended p50 / p95 (ms) |
|---|---|---|---|---|
| 1 | 80.0 | 12.3 / 13.8 | 87.3 | 11.2 / 12.9 |
| 10 | 90.4 | 32.9 / 37.6 | 94.5 | 31.3 / 34.3 |
| 25 | 90.2 | 198.0 / 211.7 | 95.4 | 185.5 / 378.7 |
| 50 | 93.1 | 458.6 / 466.8 | 97.1 | 440.7 / 812.9 |
| 100 | 93.8 | 983.3 / 1009.8 | 95.8 | 963.0 / 1305.4 |

*All requests returned HTTP 200; no errors at any level. Isolated p99 outliers of
≈4 s were observed at the onset of each burst in both regimes, attributable to
JVM JIT warm-up and per-request connection establishment in the harness; they are
reported unfiltered.*

### Table VII. Scoring-node isolation and horizontal-scaling remedy (direct `/score` load, 400 requests per level)

| Concurrency | 1 worker TPS | 1 worker p95 (ms) | 4 workers TPS | 4 workers p95 (ms) | Speed-up |
|---|---|---|---|---|---|
| 1 | 110.9 | 10.4 | 110.6 | 10.5 | 1.00× |
| 10 | 95.6 | 137.0 | **328.9** | 50.2 | **3.44×** |
| 25 | 70.3 | 479.5 | **299.0** | 148.1 | **4.25×** |
| 50 | 46.9 | 1371.8 | **253.3** | 275.3 | **5.40×** |
| 100 | 41.1 | 2984.1 | **221.9** | 551.0 | **5.40×** |

---

## PART 2 — DRAFT PAPER SECTIONS

### IV. SYSTEM METHODOLOGY

**A. Inline interception model.** RT-IIPF departs from post-facto fraud
analytics by embedding the classification decision inside the payment
transaction boundary. Upon receipt of a payment request, the switch layer
acquires pessimistic write locks on both ledger rows, applies the debit and
credit provisionally within an open ACID transaction, and suspends the
executing thread pending a verdict from an isolated scoring microservice.
A verdict of *clean* commits the ledger movement; a verdict of *fraudulent*
first persists an account lock and an audit record in an independent
transaction (`REQUIRES_NEW` propagation), then aborts the payment
transaction, rolling the provisional movement back atomically. The blocked
transfer therefore never attains durable existence in the ledger.

**B. Feature enrichment.** The client interface collects six user-entered
fields, of which three (amount, transaction type, merchant category) reach
the model. Two further features (device class, network type) are captured
autonomously by client-side telemetry, and eight (counterparty demographics,
issuing banks, hour, day, weekend flag) are resolved server-side from the
account database and the switch clock. This partition is a deliberate trust
boundary: features an adversary can forge are those where forgery increases
anomaly, while temporally and demographically decisive features are beyond
client influence.

**C. Model and calibration.** An Isolation Forest (200 estimators,
contamination 0.002) is trained on 200,000 historical transactions with no
label supervision. Raw isolation scores are mapped to [0,1] by min–max
normalization whose upper bound is winsorized at the 99.95th percentile of
the training score distribution, preventing a single extremal training point
from compressing the operational range. The production threshold τ = 0.85
was selected to bound the empirical false-positive rate below 1% (measured:
0.86%).

**D. Evaluation methodology: synthetic fraud injection.** The public
dataset's `fraud_flag` annotations were found to be statistically
uninformative: no evaluated detector, supervised or unsupervised, exceeded
ROC-AUC 0.48 against them, consistent with random assignment. Supervised
evaluation against such labels would be vacuous. We therefore adopt
perturbation-based synthetic injection: 400 attack vectors (four archetypes
× 100) are constructed by sampling genuine held-out transactions and
overwriting only the fields that define each archetype, preserving realistic
marginals in all remaining fields. Archetype B (transaction-velocity attack)
is included as a *negative control*: its constituent transfers are
individually unremarkable, and a per-transaction scorer receiving no
velocity features is expected — and confirmed — to detect none of them.
This choice quantifies a known architectural boundary rather than
overstating system capability.

### V. EXPERIMENTAL EVALUATION AND RESULTS

**A. Setup.** 250,000 transactions were split 80/20 (seed 42) into training
and clean held-out sets. All experiments share one injected evaluation set
(50,400 rows; 0.79% synthetic prevalence). Score-based baselines are
compared at an equal 1% false-positive budget, reflecting the operational
reality that an inline blocker is FPR-constrained.

**B. Detection under injection (Tables I–II).** At the production operating
point the deployed model detects 26% of off-hour drains (A), 26% of
context anomalies (D), 7% of category anomalies (C), and — as designed —
0% of velocity attacks (B), at a 0.86% false-positive rate. Overall recall
is 14.8%. Two failure mechanisms are identifiable. First, *isolation
saturation*: amounts beyond the training maximum cannot deepen their
isolation path, so archetypes defined chiefly by extremal amounts (A, C)
asymptote below the threshold (mean scores 0.781 and 0.567 respectively)
despite being obvious to inspection. Second, the *velocity blind spot* is
total, confirming that per-transaction scoring cannot substitute for
sequence-aware features.

**C. Ablation of enrichment layers (Table III).** The layers exhibit an
instructive dissociation between ranking quality and operating-point
utility. The form-only model attains the highest ROC-AUC (0.860) — its
ranking is dominated by the amount marginal, which orders archetypes A and
C above nearly all clean traffic — yet it is *operationally inert*,
detecting 1% of attacks at the deployable threshold and 0% of the
context-defined archetype D. Adding client telemetry (L2) sacrifices
global AUC (0.747) but multiplies operating-point recall twenty-two-fold
(0.010 → 0.228) and enables context-anomaly detection entirely absent at
L1 (D: 0.00 → 0.40). This supports two conclusions: (i) enrichment
features determine *which attack classes are detectable at all* at a fixed
FPR budget, and (ii) ROC-AUC is a misleading selection criterion for
FPR-constrained inline blocking; recall at the operating point is the
decision-relevant metric.

**D. Baseline comparison (Table IV).** Under an equal 1% FPR budget,
Local Outlier Factor substantially outperforms the deployed Isolation
Forest (recall 0.745 vs. 0.163; AUC 0.896 vs. 0.723), with One-Class SVM
(0.675) and even static rules (0.658) also superior on this metric. We
attribute the Isolation Forest's deficit to its known degradation on
sparse one-hot-encoded categorical spaces, where axis-parallel splits
dilute the informative numeric dimensions, compounded by the saturation
effect of §V-B. We report this negative result deliberately: it indicates
that the *architectural* contribution of RT-IIPF (inline interception with
transactional rollback) is orthogonal to, and currently bottlenecked by,
the choice of scoring model — and that a density-based scorer or a
rule/model hybrid is the immediate uplift path. The Isolation Forest
retains advantages in inference latency and training scalability that a
production selection would weigh against LOF's detection superiority.

**E. Latency and concurrency (Tables V–VII).** Under a single client the
full inline path — authentication, ledger locking, provisional movement,
scoring round-trip, and commit or rollback — completes in 11–12 ms mean
(p99 14 ms), comfortably inside the 50 ms design budget.

Under concurrent load the system exhibits a throughput ceiling of
approximately 95 transactions per second, beyond which latency grows
linearly with offered concurrency (p50 983 ms at 100 concurrent clients)
while throughput remains flat — the signature of a single saturated serial
resource. Crucially, the contended and uncontended regimes are
statistically indistinguishable (95.8 vs. 93.8 TPS at concurrency 100),
which *falsifies the expected hypothesis* that pessimistic ledger locks
held across the scoring round-trip constitute the scaling constraint.

Isolating the scoring node (Table VII) locates the bottleneck: served by a
single Python process, `/score` throughput *degrades* from 110.9 TPS at
concurrency 1 to 41.1 TPS at concurrency 100, consistent with global
interpreter lock contention among request threads executing CPU-bound
vectorized inference. Because the scoring node is stateless, the remedy is
horizontal: replicating it across four worker processes raises throughput
to 328.9 TPS at concurrency 10 and 221.9 TPS at concurrency 100 — speed-ups
of 3.4× and 5.4× respectively — while reducing p95 latency at concurrency
50 from 1372 ms to 275 ms.

This result is architecturally significant. The design decision most open
to criticism — holding database row locks across a synchronous network
call — is empirically *not* the limiting factor at the concurrency levels
examined; the limit resides in the one tier that is stateless and therefore
trivially replicable. The transactional interception mechanism and the
scoring capacity scale independently.

### VI. LIMITATIONS AND FUTURE WORK

**Population-level modeling.** The detector encodes what is anomalous for
the population, not for the account. Per-account rolling baselines
(deviation from historical amount distribution, novel-payee and
novel-device indicators) are the highest-value feature additions and are
computable from the existing audit table.

**Velocity blindness (confirmed).** The negative control quantifies a hard
boundary: 0% detection of rapid-drain sequences. Windowed velocity
features (transaction count and amount sum over 1-minute/1-hour horizons)
require one indexed query at enrichment time and a model retrain.

**Model selection.** The baseline study identifies LOF as strictly
dominant in detection at equal FPR on this feature encoding. Future work
will evaluate a two-tier scorer (fast forest prefilter; LOF confirmation)
and target-encoded categoricals to relieve the one-hot dilution.

**Graduated friction.** The prototype hard-blocks and locks at τ ≥ 0.85.
A production posture would introduce step-up authentication (OTP or
biometric) in an intermediate band, reserving hard blocks and account
locks for extreme scores, and route lock release through a support
workflow rather than permanence.

**Fail-closed availability.** Scoring-service unavailability rejects all
payments — safety is preferred to availability. A lightweight local rule
engine as degraded-mode fallback, with circuit-breaker semantics, would
bound the availability cost.

**Telemetry trust boundary.** Client-originated features (device class,
network type) are spoofable; the design partially mitigates this in that
plausible spoofing shifts transactions *toward* rarer, higher-scoring
contexts, and decisive features are server-derived. IP-derived geolocation
verified server-side would strengthen this boundary.

**Prototype security scope.** MPIN digests use unsalted SHA-256 rather
than a memory-hard KDF; transport is plaintext HTTP; sessions are
unauthenticated. These were excluded from the latency-isolation prototype
deliberately and are prerequisites for any deployment.

**Throughput ceiling and deployment scope.** The measured ceiling of ~95
TPS on a single 8-core host is an artifact of single-process inference,
not of the interception design; four-way replication of the stateless
scoring tier yields 3.4–5.4× improvement (Table VII). Validating linear
scale-out across physical hosts, and characterizing lock contention at
concurrency levels where it does become dominant, remain open. All
measurements are single-host, loopback-networked, and therefore exclude
datacenter network latency, TLS termination, and multi-tenant interference.
Isolated ≈4 s p99 outliers at burst onset (attributed to JVM JIT warm-up
and non-pooled harness connections) warrant elimination through connection
pooling and pre-warmed JIT before publication-grade tail-latency claims.
