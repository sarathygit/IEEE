"""Generate publication figures for the RT-IIPF paper.

Fig. 1  score distributions: clean traffic vs each injected archetype,
        with the production threshold marked (shows isolation saturation).
Fig. 2  ROC curves for all four detectors on the same injected set.
Fig. 3  throughput scaling: 1 worker vs 4 workers.

Outputs vector PDFs into ../paper/figs/ (IEEE column width).
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve, roc_auc_score

from evaluate import (ALL_FEATURES, SEED, PRODUCTION_THRESHOLD, N_PER_ARCHETYPE,
                      build_preprocessor, fit_forest, calibrated_scores,
                      inject_synthetics)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM

OUT = os.path.join(os.path.dirname(__file__), "..", "paper", "figs")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "figure.dpi": 300, "savefig.bbox": "tight", "axes.grid": True,
    "grid.alpha": 0.3, "grid.linewidth": 0.4,
})
COL = 3.4  # IEEE single-column width (inches)


def main():
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(os.path.join(os.path.dirname(__file__), "..",
                                  "upi_transactions_2024.csv"))
    X = df[ALL_FEATURES].copy()
    X_train, X_test = train_test_split(X, test_size=0.2, random_state=SEED)
    synth = inject_synthetics(X_test, rng)
    X_eval = pd.concat([X_test, synth[ALL_FEATURES]], ignore_index=True)
    y = np.concatenate([np.zeros(len(X_test)), np.ones(len(synth))])

    prod = fit_forest(X_train, ALL_FEATURES)
    scores = calibrated_scores(prod, X_eval)
    clean_s, synth_s = scores[:len(X_test)], scores[len(X_test):]

    # ---- Fig 1: score distributions --------------------------------------
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    bins = np.linspace(0, 1, 60)
    ax.hist(clean_s, bins=bins, density=True, alpha=0.45,
            color="#4a6fa5", label="Clean traffic")
    styles = {"A off-hour drain": "#c0392b", "B velocity (neg-ctrl)": "#7f8c8d",
              "C category anomaly": "#e67e22", "D context anomaly": "#8e44ad"}
    for name, colour in styles.items():
        s = synth_s[(synth["archetype"] == name).to_numpy()]
        ax.hist(s, bins=bins, density=True, histtype="step", lw=1.2,
                color=colour, label=name.replace(" (neg-ctrl)", " (neg. ctrl)"))
    ax.axvline(PRODUCTION_THRESHOLD, color="k", ls="--", lw=1)
    ax.text(PRODUCTION_THRESHOLD - 0.02, ax.get_ylim()[1] * 0.92,
            r"$\tau=0.85$", ha="right", fontsize=7)
    ax.set_xlabel("Normalised anomaly score")
    ax.set_ylabel("Density")
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(os.path.join(OUT, "fig1_score_distributions.pdf"))
    plt.close(fig)
    print("wrote fig1_score_distributions.pdf")

    # ---- Fig 2: ROC comparison -------------------------------------------
    pre = build_preprocessor(ALL_FEATURES)
    Xt_tr = pre.fit_transform(X_train[ALL_FEATURES])
    Xt_ev = pre.transform(X_eval[ALL_FEATURES])

    sub = rng.choice(Xt_tr.shape[0], 40_000, replace=False)
    lof = LocalOutlierFactor(n_neighbors=20, novelty=True).fit(Xt_tr[sub])
    lof_s = -lof.decision_function(Xt_ev)

    sub = rng.choice(Xt_tr.shape[0], 15_000, replace=False)
    oc = OneClassSVM(nu=0.002, kernel="rbf", gamma="scale").fit(Xt_tr[sub])
    oc_s = -oc.decision_function(Xt_ev)

    # The rule baseline emits a BINARY decision, not a ranking. Deriving a
    # continuous pseudo-score for it would be amount-dominated and therefore
    # near-oracular for the amount-defined archetypes (A, C) - an artifact of
    # the archetype design, not a property of the classifier. It is plotted
    # as its single true operating point instead.
    p99 = float(X_train["amount (INR)"].quantile(0.99))
    p95 = float(X_train["amount (INR)"].quantile(0.95))
    rule_flag = ((X_eval["amount (INR)"] > p99) |
                 ((X_eval["amount (INR)"] > p95) &
                  (X_eval["hour_of_day"] <= 5))).to_numpy()
    rule_tpr = float(rule_flag[y == 1].mean())
    rule_fpr = float(rule_flag[y == 0].mean())

    fig, ax = plt.subplots(figsize=(COL, 2.6))
    for label, s, colour in [
            ("LOF", lof_s, "#c0392b"),
            ("One-Class SVM", oc_s, "#e67e22"),
            ("Isolation Forest", scores, "#4a6fa5")]:
        fpr, tpr, _ = roc_curve(y, s)
        ax.plot(fpr, tpr, lw=1.2, color=colour,
                label=f"{label} (AUC {roc_auc_score(y, s):.3f})")
    ax.plot(rule_fpr, rule_tpr, "D", ms=5, color="#7f8c8d",
            label=f"Static rules (single op. pt.)")
    ax.plot([0, 1], [0, 1], ls=":", lw=0.8, color="k")
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("False-positive rate")
    ax.set_ylabel("True-positive rate")
    ax.legend(loc="lower right", frameon=False)
    fig.savefig(os.path.join(OUT, "fig2_roc_comparison.pdf"))
    plt.close(fig)
    print("wrote fig2_roc_comparison.pdf")

    # ---- Fig 3: scaling --------------------------------------------------
    conc = [1, 10, 25, 50]
    one_w = [55.4, 62.2, 62.3, 62.6]
    four_w = [54.5, 126.4, 194.4, 196.0]
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    ax.plot(conc, one_w, "o-", lw=1.2, ms=4, color="#c0392b",
            label="1 worker process")
    ax.plot(conc, four_w, "s-", lw=1.2, ms=4, color="#27ae60",
            label="4 worker processes")
    ax.set_xscale("log")
    ax.set_xticks(conc)
    ax.set_xticklabels([str(c) for c in conc])
    ax.set_xlabel("Concurrent clients")
    ax.set_ylabel("Throughput (txn/s)")
    ax.legend(frameon=False)
    fig.savefig(os.path.join(OUT, "fig3_scaling.pdf"))
    plt.close(fig)
    print("wrote fig3_scaling.pdf")


if __name__ == "__main__":
    main()
