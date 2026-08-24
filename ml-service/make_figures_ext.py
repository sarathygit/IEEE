"""Additional figures for the journal-length manuscript.

Fig. 4  threshold sensitivity: recall vs. genuine-customer block rate,
        showing that no operating point of the deployed scorer is
        simultaneously effective and operationally tolerable.
Fig. 5  per-archetype recall, Isolation Forest vs. LOF at matched FPR.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "paper", "figs")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "figure.dpi": 300, "savefig.bbox": "tight", "axes.grid": True,
    "grid.alpha": 0.3, "grid.linewidth": 0.4,
})
COL = 3.4

res = json.load(open(os.path.join(HERE, "evaluation_extended.json")))


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"))
    plt.close(fig)
    print("wrote", name)


# ---- Fig 4: threshold sensitivity ---------------------------------------
sweep = res["threshold_sweep"]
tau = [r["tau"] for r in sweep]
recall = [r["recall"] for r in sweep]
blocked = [r["blocked_per_100k_genuine"] for r in sweep]

fig, ax1 = plt.subplots(figsize=(COL, 2.3))
l1, = ax1.plot(tau, recall, "o-", lw=1.3, ms=4, color="#2c7fb8", label="Recall")
ax1.set_xlabel(r"Threshold $\tau$")
ax1.set_ylabel("Recall on injected fraud", color="#2c7fb8")
ax1.tick_params(axis="y", labelcolor="#2c7fb8")
ax1.set_ylim(0, 0.65)

ax2 = ax1.twinx()
l2, = ax2.plot(tau, blocked, "s--", lw=1.3, ms=4, color="#c0392b",
               label="Genuine blocked / 100k")
ax2.set_ylabel("Genuine customers blocked\nper 100k transactions", color="#c0392b")
ax2.tick_params(axis="y", labelcolor="#c0392b")
ax2.set_yscale("log")
ax2.grid(False)

ax1.axvline(0.85, color="k", ls=":", lw=1)
ax1.text(0.856, 0.30, "deployed $\\tau$", fontsize=6.5, rotation=90, va="center")
ax1.legend(handles=[l1, l2], loc="upper right", frameon=False, fontsize=6.5,
           bbox_to_anchor=(1.0, 1.02))
save(fig, "fig4_threshold_sensitivity")

# ---- Fig 5: per-archetype, IF vs LOF ------------------------------------
per = res["scorer_substitution"]["per_archetype"]
names = list(per.keys())
short = ["A\noff-hour\ndrain", "B\nvelocity\n(neg. ctrl)",
         "C\ncategory\nanomaly", "D\ncontext\nanomaly"]
iforest = [per[n]["iforest_recall"] for n in names]
lofv = [per[n]["lof_recall"] for n in names]

x = np.arange(len(names))
w = 0.38
fig, ax = plt.subplots(figsize=(COL, 2.3))
ax.bar(x - w/2, iforest, w, color="#4a6fa5", label="Isolation Forest")
ax.bar(x + w/2, lofv, w, color="#c0392b", label="LOF (matched FPR)")
ax.set_xticks(x)
ax.set_xticklabels(short, fontsize=6.5)
ax.set_ylabel("Recall")
ax.set_ylim(0, 1.28)
ax.legend(frameon=False, loc="upper left", fontsize=6.5, ncol=2,
          bbox_to_anchor=(0.0, 1.02))
for xi, v in zip(x - w/2, iforest):
    ax.text(xi, v + 0.03, f"{v:.2f}", ha="center", fontsize=6)
for xi, v in zip(x + w/2, lofv):
    ax.text(xi, v + 0.03, f"{v:.2f}", ha="center", fontsize=6)
save(fig, "fig5_scorer_substitution")
