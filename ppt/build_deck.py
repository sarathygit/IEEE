"""Fill the Phase-I review template with RT-IIPF / FinGuard-AI content.

Text is written run-by-run so the template's fonts, sizes, colours and
bullet formatting survive (assigning text_frame.text would collapse every
paragraph to one unstyled run).
"""
import copy
import math

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt, Inches

EMU_IN = 914400
GLYPH_W = 0.50     # avg glyph width as fraction of font size
LINE_H = 1.24
BOX_PAD = 0.12     # per-side internal padding, inches


def _est_height_in(lines, font_pt, width_in):
    usable = max(width_in - 2 * BOX_PAD, 0.3)
    char_w = (font_pt * GLYPH_W) / 72.0
    per_line = max(int(usable / char_w), 1)
    total = sum(max(1, math.ceil(len(ln) / per_line)) for ln in lines)
    return total * font_pt * LINE_H / 72.0


def clear_stale_autofit(shape):
    """Drop the template's cached fontScale/lnSpcReduction. Those were
    computed for the template's own (shorter) text; leaving them in place
    makes PowerPoint render our longer text at the wrong scale until the
    box is next edited."""
    bp = shape.text_frame._txBody.find(qn('a:bodyPr'))
    if bp is None:
        return
    na = bp.find(qn('a:normAutofit'))
    if na is not None:
        na.attrib.pop('fontScale', None)
        na.attrib.pop('lnSpcReduction', None)


def fit_font(shape, lines, max_pt, min_pt=8.0):
    """Largest font size (<= max_pt) whose estimated height fits the shape."""
    w_in = shape.width / EMU_IN
    h_in = shape.height / EMU_IN
    pt = max_pt
    while pt > min_pt and _est_height_in(lines, pt, w_in) > h_in:
        pt -= 0.5
    return pt

SRC = "scaffold.pptx"
OUT = "RT-IIPF_Phase1_Review.pptx"
DATE = "23 July 2026"

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def set_fitted(shape, lines, max_pt):
    """Write lines at the largest size that fits, and clear stale autofit."""
    clear_stale_autofit(shape)
    pt = fit_font(shape, lines, max_pt)
    set_lines(shape, lines, size=pt)
    return pt


def set_lines(shape, lines, size=None):
    """Replace a text frame's paragraphs, cloning the first paragraph's
    formatting (and its first run's) for every new line."""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    if not p0.runs:
        p0.add_run()
    proto_p = copy.deepcopy(p0._p)

    for extra in list(tf.paragraphs)[1:]:
        extra._p.getparent().remove(extra._p)

    for i, line in enumerate(lines):
        if i == 0:
            para = tf.paragraphs[0]
        else:
            new_p = copy.deepcopy(proto_p)
            tf._txBody.append(new_p)
            para = tf.paragraphs[-1]
        for r in list(para.runs)[1:]:
            r._r.getparent().remove(r._r)
        if not para.runs:
            para.add_run()
        para.runs[0].text = line
        if size:
            para.runs[0].font.size = Pt(size)


def find(slide, predicate):
    for sh in slide.shapes:
        if predicate(sh):
            return sh
    return None


def body_of(slide, skip_texts=()):
    """The main content placeholder: largest text shape that isn't the
    title, date, footer or slide number."""
    cands = []
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text.strip()
        if not t or t in skip_texts:
            continue
        if t == DATE or t.startswith("School of Computing") or t.isdigit():
            continue
        cands.append(sh)
    return max(cands, key=lambda s: s.width * s.height) if cands else None


def title_of(slide):
    for sh in slide.shapes:
        if sh.has_text_frame and sh.is_placeholder:
            try:
                if sh.placeholder_format.type == 13 or "Title" in sh.name:
                    return sh
            except ValueError:
                pass
    tops = [sh for sh in slide.shapes
            if sh.has_text_frame and sh.text_frame.text.strip()]
    return min(tops, key=lambda s: s.top) if tops else None


def fill_table(shape, rows, size=8.0, header_size=8.5,
               header_h=None, row_h=None, bottom_limit_in=6.80):
    """Write a list-of-lists into an existing table, adding/removing rows
    to match, and preserving each cell's run formatting.

    Row heights in the template are a *minimum*, and the template's own
    1.82in rows overflow the slide as soon as a third data row is added.
    When header_h/row_h are given they are applied so the table ends above
    `bottom_limit_in` (the footer band)."""
    tbl = shape.table
    need, have = len(rows), len(tbl.rows)
    if need > have:
        proto = copy.deepcopy(tbl._tbl.tr_lst[-1])
        for _ in range(need - have):
            tbl._tbl.append(copy.deepcopy(proto))
    elif need < have:
        for tr in tbl._tbl.tr_lst[need:]:
            tbl._tbl.remove(tr)

    if row_h is None:
        avail = bottom_limit_in - shape.top / EMU_IN
        header_h = header_h or 0.50
        row_h = max((avail - header_h) / max(len(rows) - 1, 1), 0.30)
    for i, r in enumerate(tbl.rows):
        r.height = Inches(header_h if i == 0 else row_h)

    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            if c >= len(tbl.columns):
                break
            cell = tbl.cell(r, c)
            tf = cell.text_frame
            for extra in list(tf.paragraphs)[1:]:
                extra._p.getparent().remove(extra._p)
            para = tf.paragraphs[0]
            for rr in list(para.runs)[1:]:
                rr._r.getparent().remove(rr._r)
            if not para.runs:
                para.add_run()
            para.runs[0].text = val
            para.runs[0].font.size = Pt(header_size if r == 0 else size)
            para.runs[0].font.bold = (r == 0)



def style_as_header(shape, text_startswith, size=None):
    """Make a line inside a bulleted body act as a section header:
    bold, and with its bullet suppressed."""
    from pptx.oxml.ns import qn as _qn
    for para in shape.text_frame.paragraphs:
        if para.runs and para.runs[0].text.startswith(text_startswith):
            para.runs[0].font.bold = True
            if size:
                para.runs[0].font.size = Pt(size)
            pPr = para._p.get_or_add_pPr()
            for tag in ('a:buChar', 'a:buAutoNum', 'a:buNone'):
                for el in pPr.findall(_qn(tag)):
                    pPr.remove(el)
            pPr.append(pPr.makeelement(_qn('a:buNone'), {}))
            return True
    return False


NOTES = {
 1: "Introduce the team and the title. One line: today's fraud systems detect "
    "AFTER money moves; we block BEFORE it moves.",
 2: "Walk the agenda in ten seconds.",
 3: "Key sentence: a blocked transfer never exists in the ledger, so there is "
    "nothing to claw back. Mention the 11-12 ms measured decision time.",
 4: "Five objectives. Emphasise objective 2 (atomic rollback with surviving "
    "audit) - that is the novel engineering contribution.",
 5: "State the base paper and, importantly, the gap: it scores transactions but "
    "never integrates with the transaction boundary, so detection stays advisory.",
 6: "Foundational anomaly detection. Isolation Forest is what we deployed; LOF "
    "and One-Class SVM are our comparison baselines.",
 7: "Evaluation methodology and the two fraud surveys that frame the field's "
    "reliance on supervised learning.",
 8: "Recent UPI-specific work. Note that all of it scores post-transaction.",
 9: "Applied and comparative studies. The last row is the direct LOF vs "
    "Isolation Forest comparison on card data.",
 10:"The critical inference is the third one: no reviewed work ties the fraud "
    "verdict to database transaction semantics. That gap is our project.",
 11:"Walk the four numbered steps, then the advantages. If asked how the audit "
    "row survives a rollback: it is written in a separate REQUIRES_NEW transaction.",
 12:"Trace one payment left to right, then down to the ledger. Stress that the "
    "money is already debited but NOT committed while the AI is deciding.",
 13:"Six modules. Testing and Evaluation covers commit, rollback, account lock "
    "and fail-closed paths plus latency benchmarking.",
 14:"The last two items are what overcome the gap in existing work: pessimistic "
    "locking during the scoring hop, and exception-driven atomic rollback.",
 15:"Alphabetical order. Four IEEE Xplore references still need complete author "
    "lists before submission.",
 16:"Thank the panel and invite questions. Offer the live demo if time permits.",
}


def add_notes(prs):
    for i, slide in enumerate(prs.slides, 1):
        if i in NOTES:
            slide.notes_slide.notes_text_frame.text = NOTES[i]


# --------------------------------------------------------------------------
# content
# --------------------------------------------------------------------------

TITLE = ("RT-IIPF: REAL-TIME INLINE INTERCEPTION OF FRAUDULENT UPI "
         "TRANSACTIONS USING UNSUPERVISED ANOMALY DETECTION AND "
         "TRANSACTIONAL ROLLBACK")

ABSTRACT = (
    "Conventional payment fraud systems operate retrospectively: a transaction "
    "settles, logs are analysed later, and recovery is attempted after the money "
    "has already moved. On real-time rails such as the Unified Payments Interface "
    "(UPI), funds are forwarded and withdrawn within minutes, making recovery "
    "largely infeasible. This project proposes RT-IIPF, a framework that relocates "
    "the fraud decision inside the payment transaction itself. When a payment "
    "arrives, the Spring Boot switch acquires pessimistic locks on both ledger "
    "rows, applies the debit and credit provisionally without committing, and "
    "suspends the executing thread while an isolated Python microservice scores "
    "the transaction using an unsupervised Isolation Forest. A clean verdict "
    "commits the ledger; a fraudulent verdict triggers an atomic rollback and "
    "locks the payer account, while the audit record survives the rollback through "
    "an independent transaction. The prototype achieves an end-to-end decision in "
    "11-12 ms, so a blocked transfer never attains durable existence in the ledger "
    "and there is nothing to claw back.")

OBJECTIVES = [
    "Design an inline interception pipeline that suspends a UPI payment "
    "mid-transaction and arbitrates its commit on a machine-learning verdict.",
    "Implement atomic rollback with a surviving audit trail, so a blocked "
    "transfer leaves no ledger effect while the security response persists.",
    "Train an unsupervised Isolation Forest on 250,000 real UPI transactions "
    "that requires no fraud labels and can flag previously unseen patterns.",
    "Enrich six user-entered fields into a 13-feature vector using client "
    "telemetry and server-side data the client cannot forge.",
    "Validate the sub-50 ms design budget through latency and concurrency "
    "benchmarking of the complete three-service system.",
]

BASE_PAPER = [
    "Base Paper Title: Enhancing Digital Payment Security: UPI Fraud Detection "
    "with Advanced Machine Learning Algorithms",
    "Year: 2025",
    "Journal / Conference: IEEE Xplore Conference Publication",
    "",
    "Method: Hybrid Deep Q-Network (DQN) with XGBoost - reinforcement learning "
    "for adaptive policy combined with gradient boosting for tabular classification.",
    "",
    "Identified Gap: The model scores transactions but is not integrated into the "
    "payment transaction boundary; detection remains advisory rather than "
    "preventive, and no rollback or ledger-integrity mechanism is provided.",
]

LIT_HEADER = ["AUTHOR", "JOURNAL NAME & YEAR", "TITLE", "DESCRIPTION",
              "PROS", "CONS"]

LIT_PAPERS = [
    # ---- slide 1/4 : foundational anomaly detection ----
    ["Liu, F.T., Ting, K.M., Zhou, Z.-H.",
     "IEEE ICDM, 2008",
     "Isolation Forest",
     "Isolates anomalies by random axis-parallel partitioning; anomaly score "
     "derived from average isolation depth.",
     "Linear time complexity, low memory, needs no distance or density "
     "computation - suited to latency-bound inference.",
     "Degrades on sparse one-hot categorical spaces; scores saturate for "
     "extreme values; no per-entity context."],
    ["Breunig, M.M., Kriegel, H.-P., Ng, R.T., Sander, J.",
     "ACM SIGMOD, 2000",
     "LOF: Identifying Density-Based Local Outliers",
     "Assigns outlierness by comparing a point's local reachability density "
     "with that of its neighbours.",
     "Detects local outliers that global methods miss; strong recall in our "
     "own comparative evaluation.",
     "Requires a reference set resident in memory; neighbour search cost "
     "grows with reference size."],
    ["Scholkopf, B., Platt, J.C., Shawe-Taylor, J., et al.",
     "Neural Computation, 2001",
     "Estimating the Support of a High-Dimensional Distribution",
     "One-Class SVM estimates a support boundary enclosing the normal class "
     "in kernel space.",
     "Principled support estimation; kernel choice allows non-linear "
     "decision boundaries.",
     "Training cost is quadratic in sample size; performance sensitive to "
     "kernel and nu selection."],

    # ---- slide 2/4 : evaluation methodology and fraud surveys ----
    ["Campos, G.O., Zimek, A., Sander, J., et al.",
     "Data Mining and Knowledge Discovery, 2016",
     "On the Evaluation of Unsupervised Outlier Detection",
     "Systematic comparison of unsupervised detectors across measures and "
     "benchmark datasets.",
     "Establishes evaluation pitfalls and standardised benchmarking practice "
     "for unsupervised detection.",
     "Does not address deployment constraints such as inference latency or "
     "false-positive budgets."],
    ["Abdallah, A., Maarof, M.A., Zainal, A.",
     "Journal of Network and Computer Applications, 2016",
     "Fraud Detection System: A Survey",
     "Surveys fraud detection systems across credit card, telecommunication "
     "and insurance domains.",
     "Broad taxonomy of fraud types, detection techniques and evaluation "
     "criteria.",
     "Predates modern real-time rails; no treatment of transactional "
     "integration or rollback semantics."],
    ["Adewumi, A.O., Akinyelu, A.A.",
     "Int. J. of System Assurance Engineering and Management, 2017",
     "A Survey of ML and Nature-Inspired Credit Card Fraud Detection Techniques",
     "Reviews machine-learning and nature-inspired algorithms applied to "
     "card fraud detection.",
     "Comparative view of algorithm families with reported accuracy ranges.",
     "Card-centric; does not cover UPI or any sub-second real-time payment "
     "rail."],

    # ---- slide 3/4 : recent UPI-specific work ----
    ["Thayanidhi, V., Srivarshan, M., Shalini, M.",
     "Springer, ICSMDI 2025 (pub. 2026)",
     "UPI Fraud Detection Using Machine Learning",
     "Analyses UPI transaction patterns and user behaviour using decision "
     "trees, random forests and neural networks.",
     "Directly targets the UPI rail; reports real-time analysis of "
     "behavioural patterns.",
     "Supervised approach requiring labelled fraud data; detection is "
     "post-transaction rather than inline."],
    ["Jani, R., Kumar, M.R., Gumasthi, N., Singla, S., Kailasam, T.",
     "Springer, AIAI 2025",
     "Reinforcement Learning for UPI Fraud Detection: Actor Critic "
     "Optimization Approach",
     "Applies actor-critic reinforcement learning to adapt the fraud "
     "decision policy over time.",
     "Adapts to evolving fraud strategies without full retraining.",
     "Training complexity and reward-design sensitivity; no ledger-level "
     "enforcement mechanism."],
    ["[Verify authors on IEEE Xplore]",
     "IEEE Conference Publication, 2025",
     "Enhancing Digital Payment Security: UPI Fraud Detection with Advanced "
     "Machine Learning Algorithms",
     "Hybrid Deep Q-Network with XGBoost combining adaptive learning and "
     "gradient-boosted tabular classification.",
     "Strong reported accuracy on tabular UPI data; adaptive to drift.",
     "Advisory scoring only - not integrated into the transaction boundary; "
     "no rollback or account-lock mechanism."],

    # ---- slide 4/4 : recent applied and comparative work ----
    ["[Verify authors on IEEE Xplore]",
     "IEEE Conference Publication, 2025",
     "PaySafe AI: Intelligent Fraud Detection for UPI Transactions using "
     "Machine Learning",
     "Normalises typical account activity and classifies sequences of "
     "transactions as fraudulent or genuine.",
     "Sequence-aware modelling captures behavioural drift over time.",
     "No inline commit/rollback integration; sequence features require "
     "history unavailable at first transaction."],
    ["[Verify authors on IEEE Xplore]",
     "IEEE Conference Publication, 2025",
     "Machine Learning-Driven Detection of UPI Fraudulent Activities",
     "Multimodal pipeline processing transaction records, QR-code images and "
     "audio from vishing attempts.",
     "Covers a broad attack surface beyond the transaction record itself.",
     "Heavy multimodal pipeline unsuitable for a sub-50 ms inline decision "
     "path."],
    ["[Verify authors on IEEE Xplore]",
     "IEEE Conference Publication, 2022",
     "Degree of Accuracy in Credit Card Fraud Detection Using LOF and Isolation Forest",
     "Comparative evaluation of LOF and Isolation Forest on credit card "
     "transaction data.",
     "Direct empirical comparison of the two detectors central to this work.",
     "Card dataset only; no deployment architecture, latency measurement or "
     "concurrency analysis."],
]

INFERENCES = [
    "Existing UPI fraud research is overwhelmingly post-transaction: models "
    "score a payment after it settles, leaving recovery as the only remedy.",
    "Supervised approaches dominate, yet real fraud labels are scarce, delayed "
    "and unable to describe novel attack patterns.",
    "No reviewed work integrates the fraud verdict with database transaction "
    "semantics - none provides atomic rollback of a flagged transfer.",
    "Reported accuracy is rarely paired with latency measurement, so the "
    "feasibility of inline deployment remains unestablished.",
    "Evaluation typically reports ROC-AUC alone, which is misleading for a "
    "blocker constrained by an operational false-positive budget.",
]

PROPOSED_1 = [
    "The React client captures payment inputs (payee VPA, amount, transaction "
    "type, merchant category, MPIN) together with silent device telemetry, and "
    "posts them to the Spring Boot switch.",
    "The switch authenticates the MPIN, acquires PESSIMISTIC_WRITE locks on the "
    "payer and payee ledger rows in ascending id order, and applies the debit "
    "and credit without committing them.",
    "The request thread is suspended while the FastAPI microservice scores a "
    "13-feature vector with an Isolation Forest and returns a normalised "
    "anomaly score with a binary verdict.",
    "A clean verdict commits the ledger; a fraudulent verdict writes the audit "
    "row and account lock in an independent transaction, then throws an "
    "exception that rolls the money movement back atomically.",
    "Advantages of the Proposed System",
    "Blocks fraud before settlement rather than detecting it afterwards.",
    "Guarantees ledger integrity through ACID rollback with a surviving audit trail.",
    "Requires no fraud labels, so novel attack patterns can be flagged.",
    "Fails closed: an unreachable scoring node rejects payments rather than "
    "admitting them unscored.",
    "Achieves an end-to-end decision in 11-12 ms, within the sub-50 ms budget.",
]

MODULES = [
    ["Modules", "Activities"],
    ["Requirement Analysis",
     "Study UPI transaction flows and fraud patterns; define the sub-50 ms "
     "inline decision budget and the fail-closed safety policy."],
    ["Data Preparation",
     "Ingest 250,000 UPI transactions; clean and encode 13 pre-settlement "
     "features; exclude post-settlement fields that would leak the outcome."],
    ["Model Development",
     "Train the unsupervised Isolation Forest, calibrate scores to [0,1] with "
     "a winsorised ceiling, and serialise the model bundle to .joblib."],
    ["Backend & Ledger Development",
     "Build the Spring Boot switch with H2 ledger, pessimistic row locking, "
     "MPIN authentication, and the rollback-with-surviving-audit pattern."],
    ["Service Integration",
     "Connect the React client, Spring Boot switch and FastAPI scoring node "
     "over REST with bounded timeouts and fail-closed error handling."],
    ["Testing & Evaluation",
     "Verify commit, rollback, account-lock and fail-closed paths; benchmark "
     "latency, concurrency and detection under synthetic fraud injection."],
]

ALGORITHM = [
    "Feature Assembly: 6 user inputs enriched to a 13-dimensional vector using "
    "client telemetry and server-resolved account and temporal data",
    "Preprocessing: standard scaling of numeric features and one-hot encoding "
    "of categorical features (unknown categories handled safely)",
    "Unsupervised Isolation Forest (200 estimators) for anomaly scoring",
    "Score Calibration: min-max normalisation to [0,1] with the ceiling "
    "winsorised at the 99.95th percentile of the training distribution",
    "Threshold Decision Rule: is_fraud = 1 when score >= 0.85, else 0",
    "Concurrency Control: PESSIMISTIC_WRITE row locking in ascending account-id "
    "order to prevent deadlock during the scoring hop",
    "Atomic Rollback: FraudulentTransactionException triggers ledger rollback "
    "while REQUIRES_NEW propagation preserves the audit row and account lock",
    "",
    "*The inline interception and rollback mechanism overcomes the key "
    "limitation of existing work, in which fraud is scored only after the "
    "transaction has already settled.",
]

REFERENCES = [
    "Abdallah, A., Maarof, M. A., & Zainal, A. (2016). Fraud detection system: "
    "A survey. Journal of Network and Computer Applications, 68, 90-113.",
    "Adewumi, A. O., & Akinyelu, A. A. (2017). A survey of machine-learning and "
    "nature-inspired based credit card fraud detection techniques. International "
    "Journal of System Assurance Engineering and Management, 8(2), 937-953.",
    "Breunig, M. M., Kriegel, H.-P., Ng, R. T., & Sander, J. (2000). LOF: "
    "Identifying density-based local outliers. Proceedings of the ACM SIGMOD "
    "International Conference on Management of Data, 93-104.",
    "Campos, G. O., Zimek, A., Sander, J., et al. (2016). On the evaluation of "
    "unsupervised outlier detection: measures, datasets, and an empirical study. "
    "Data Mining and Knowledge Discovery, 30(4), 891-927.",
    "Jani, R., Kumar, M. R., Gumasthi, N., Singla, S., & Kailasam, T. (2025). "
    "Reinforcement learning for UPI fraud detection: Actor critic optimization "
    "approach. Artificial Intelligence Applications and Innovations (AIAI 2025), "
    "Springer.",
    "Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation forest. "
    "Proceedings of the 8th IEEE International Conference on Data Mining, "
    "413-422.",
    "Scholkopf, B., Platt, J. C., Shawe-Taylor, J., Smola, A. J., & Williamson, "
    "R. C. (2001). Estimating the support of a high-dimensional distribution. "
    "Neural Computation, 13(7), 1443-1471.",
    "Thayanidhi, V., Srivarshan, M., & Shalini, M. (2026). UPI fraud detection "
    "using machine learning. International Conference on Smart Data Intelligence "
    "(ICSMDI 2025), Springer.",
    "",
    "[Add the four IEEE Xplore conference references cited in the Literature "
    "Survey with complete author lists, and any further papers needed to reach "
    "the required minimum of 12.]",
]


def main():
    prs = Presentation(SRC)
    S = prs.slides

    # ---- 1. title -------------------------------------------------------
    s = S[0]
    for sh in s.shapes:
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text
        if "MULTIMODAL MEDICINAL" in t:
            # The template stored 71pt text with normAutofit fontScale=25%.
            # Clear that cached scale and set a real size, otherwise the run
            # inherits a small default and is then shrunk to a quarter of it.
            clear_stale_autofit(sh)
            set_lines(sh, [TITLE], size=16)
            # Nudge clear of the 3-line department heading above it.
            sh.top = Inches(3.25)
            sh.left = Inches(0.55)
            sh.width = Inches(8.9)
            sh.height = Inches(1.5)
        elif "PROJECT STUDENTS" in t:
            students = [
                "PROJECT STUDENTS                              GUIDE",
                "[Student Name 1], [Reg. No.]                  [Guide Name]",
                "[Student Name 2], [Reg. No.]                  Assistant Professor, CSE",
            ]
            print("  title block   @", set_fitted(sh, students, 18), "pt")

    # ---- 3. abstract ----------------------------------------------------
    print("  abstract      @", set_fitted(body_of(S[2], skip_texts=("ABSTRACT",)), [ABSTRACT], 14), "pt")

    # ---- 4. objectives --------------------------------------------------
    print("  objectives    @", set_fitted(body_of(S[3], skip_texts=("OBJECTIVE(S)",)), OBJECTIVES, 16), "pt")

    # ---- 5. base paper --------------------------------------------------
    print("  base paper    @", set_fitted(body_of(S[4], skip_texts=("Base Paper Details",)), BASE_PAPER, 15), "pt")

    # ---- 6-9. literature survey (4 slides x 3 papers) -------------------
    for i in range(4):
        slide = S[5 + i]
        title_of(slide).text_frame.paragraphs[0].runs[0].text = \
            f"LITERATURE SURVEY({i + 1}/4)"
        tbl_shape = find(slide, lambda sh: sh.has_table)
        fill_table(tbl_shape, [LIT_HEADER] + LIT_PAPERS[i*3:(i+1)*3],
                   size=7.5, header_size=8.0, header_h=0.42)

    # ---- 10. inferences -------------------------------------------------
    print("  inferences    @", set_fitted(
        body_of(S[9], skip_texts=("INFERENCES FROM LITERATURE SURVEY",)),
        INFERENCES, 16), "pt")

    # ---- 11. proposed system 1/4 ---------------------------------------
    print("  proposed 1/4  @", set_fitted(
        body_of(S[10], skip_texts=("PROPOSED SYSTEM (1/4)",)), PROPOSED_1, 14), "pt")

    # ---- 12. proposed system 2/4 : architecture image -------------------
    slide = S[11]
    pic = find(slide, lambda sh: sh.shape_type == 13)
    if pic is not None:
        left, top, width = pic.left, pic.top, pic.width
        pic._element.getparent().remove(pic._element)
    else:
        left, top, width = Inches(0.4), Inches(1.6), Inches(9.2)
    from PIL import Image
    iw, ih = Image.open("architecture.png").size
    width = Inches(9.2)
    height = int(width * ih / iw)
    left = int((prs.slide_width - width) / 2)
    top = Inches(1.75)
    slide.shapes.add_picture("architecture.png", left, top, width, height)

    # ---- 13. modules table ---------------------------------------------
    fill_table(find(S[12], lambda sh: sh.has_table), MODULES,
               size=10.0, header_size=11.0, header_h=0.42)

    # ---- 14. algorithm --------------------------------------------------
    print("  algorithm     @", set_fitted(
        body_of(S[13], skip_texts=("PROPOSED SYSTEM-Algorithm(4/4)",)), ALGORITHM, 15), "pt")

    # ---- 15. references -------------------------------------------------
    print("  references    @", set_fitted(body_of(S[14], skip_texts=("References",)), REFERENCES, 12), "pt")

    # section header inside the proposed-system bullets
    style_as_header(body_of(S[10], skip_texts=("PROPOSED SYSTEM (1/4)",)),
                    "Advantages of the Proposed System")

    add_notes(prs)
    prs.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
