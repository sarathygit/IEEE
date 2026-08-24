"""Architecture diagram for the Phase-I review deck (PROPOSED SYSTEM 2/4).

Box heights are computed from content so text can never overflow.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

NAVY = "#1E2761"
TEAL = "#00707B"
CRIM = "#B3261E"
GREY = "#4A5560"
LIGHT = "#EDF0F5"

TITLE_DROP = 5.0     # title baseline below box top
PORT_DROP = 5.0      # port baseline below title
FIRST_LINE = 5.6     # first body line below port
LEAD = 4.6           # body line spacing
PAD_BOTTOM = 4.4     # clear space under last line


def box_height(n_lines):
    return TITLE_DROP + PORT_DROP + FIRST_LINE + (n_lines - 1) * LEAD + PAD_BOTTOM


W, H = 142.0, 90.0
fig, ax = plt.subplots(figsize=(14.2, 9.0))
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")


def box(x, top, w, title, port, lines, edge, fill="white"):
    """Draw a box whose TOP edge is at `top`; height derives from content."""
    h = box_height(len(lines))
    y = top - h
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.0,rounding_size=1.4",
                 linewidth=2.0, edgecolor=edge, facecolor=fill, zorder=2))
    ax.text(x + w/2, top - TITLE_DROP, title, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color=edge, zorder=3)
    ax.text(x + w/2, top - TITLE_DROP - PORT_DROP, port, ha="center",
            va="center", fontsize=8.2, color=edge, zorder=3)
    ly = top - TITLE_DROP - PORT_DROP - FIRST_LINE
    for i, ln in enumerate(lines):
        ax.text(x + 3.0, ly - i*LEAD, ln, ha="left", va="center",
                fontsize=8.4, color="#2A2A2A", zorder=3)
    return y  # bottom edge


def arrow(x1, y1, x2, y2, colour):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=14, linewidth=1.8, color=colour, zorder=1))


def alabel(x, y, text, colour):
    ax.text(x, y, text, ha="center", va="center", fontsize=7.6, color=colour,
            fontweight="bold", zorder=4, linespacing=1.55,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none"))


TOP = 80.0

box(1.0, TOP, 33.0, "REACT CLIENT", "Port 5173",
    ["Payment console:", "VPA · amount · type · MCC · MPIN",
     "Silent device telemetry capture", "Live audit-log monitor"], NAVY)

sw_bottom = box(47.0, TOP, 48.0, "SPRING BOOT SWITCH", "Port 8081",
                ["1   Authenticate MPIN (SHA-256)",
                 "2   PESSIMISTIC_WRITE row locks",
                 "3   Provisional debit / credit (uncommitted)",
                 "4   Thread suspended pending verdict",
                 "5   COMMIT   or   ROLLBACK + account lock"],
                NAVY, LIGHT)

box(108.0, TOP, 33.0, "FASTAPI AI CORE", "Port 8001",
    ["Isolation Forest (.joblib)", "13-feature vector",
     "Normalised score [0, 1]", "is_fraud = score ≥ 0.85"], TEAL)

LEDGER_TOP = sw_bottom - 8.0
box(47.0, LEDGER_TOP, 48.0, "H2 IN-MEMORY LEDGER", "Spring Data JPA",
    ["users  ·  balances  ·  transaction_logs",
     "Single ACID transaction boundary",
     "REQUIRES_NEW txn keeps audit + lock through rollback"],
    GREY, "#F6F7F9")

# ---- flows: arrows sit in the 13-unit gaps between boxes ----
arrow(34.0, TOP - 9.0, 47.0, TOP - 9.0, NAVY)
alabel(40.5, TOP - 4.2, "POST /upi/pay\n+ telemetry", NAVY)

arrow(47.0, TOP - 26.0, 34.0, TOP - 26.0, CRIM)
alabel(40.5, TOP - 31.0, "SUCCESS /\nBLOCKED", CRIM)

arrow(95.0, TOP - 9.0, 108.0, TOP - 9.0, TEAL)
alabel(101.5, TOP - 4.2, "13 features", TEAL)

arrow(108.0, TOP - 26.0, 95.0, TOP - 26.0, TEAL)
alabel(101.5, TOP - 30.5, "score + verdict", TEAL)

arrow(71.0, sw_bottom, 71.0, LEDGER_TOP, NAVY)
alabel(71.0, sw_bottom - 5.0, "lock rows  ·  commit / rollback", NAVY)

ax.text(W/2, 86.5, "RT-IIPF  —  INLINE INTERCEPTION DATA FLOW",
        ha="center", va="center", fontsize=13.5, fontweight="bold", color=NAVY)
ax.text(W/2, 1.8,
        "Funds are held mid-transaction; the ledger commits only after the AI verdict returns"
        "   ·   measured end-to-end latency 11–12 ms",
        ha="center", va="center", fontsize=8.8, style="italic", color=GREY)

fig.savefig("architecture.png", dpi=200, bbox_inches="tight", facecolor="white")
print("wrote architecture.png  (ledger bottom at y =",
      round(LEDGER_TOP - box_height(3), 1), ")")
