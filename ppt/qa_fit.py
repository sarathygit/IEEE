"""Approximate text-fit QA for the deck.

No LibreOffice/PowerPoint on this host, so slides cannot be rasterised.
This estimates rendered text height from character count, font size and
shape width, and flags shapes whose text plausibly overflows. Estimates
are deliberately conservative (assume a fairly wide average glyph), so a
PASS here still warrants a human look, but a FAIL is almost certainly real.
"""
import math
import sys

from pptx import Presentation
from pptx.util import Emu

EMU_IN = 914400
# average glyph width as a fraction of font size, for a proportional face
GLYPH_W = 0.50
LINE_H = 1.22          # line height multiple
CELL_PAD_IN = 0.10     # per-side padding inside table cells
BOX_PAD_IN = 0.10


def est_lines(text, font_pt, width_in, pad_in):
    usable = max(width_in - 2*pad_in, 0.2)
    char_w_in = (font_pt * GLYPH_W) / 72.0
    per_line = max(int(usable / char_w_in), 1)
    lines = 0
    for para in text.split("\n"):
        lines += max(1, math.ceil(len(para) / per_line))
    return lines


def est_height_in(text, font_pt, width_in, pad_in):
    return est_lines(text, font_pt, width_in, pad_in) * font_pt * LINE_H / 72.0


def shape_font(shape, default=18.0):
    sizes = []
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            if r.font.size:
                sizes.append(r.font.size.pt)
    return max(sizes) if sizes else default


def main(path):
    prs = Presentation(path)
    problems = []

    for idx, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            # ---- plain text shapes ----
            if sh.has_text_frame and sh.text_frame.text.strip():
                txt = sh.text_frame.text
                if len(txt) < 25:
                    continue
                w_in = sh.width / EMU_IN
                h_in = sh.height / EMU_IN
                fpt = shape_font(sh)
                need = est_height_in(txt, fpt, w_in, BOX_PAD_IN)
                if need > h_in * 1.02:
                    problems.append(
                        (idx, sh.name[:26], f"text {len(txt)}ch @{fpt:.0f}pt",
                         f"needs ~{need:.2f}in in {h_in:.2f}in box",
                         need / h_in))

            # ---- tables ----
            if sh.has_table:
                tbl = sh.table
                col_in = [c.width / EMU_IN for c in tbl.columns]
                total_need = 0.0
                for r, row in enumerate(tbl.rows):
                    row_need = 0.0
                    for c, cell in enumerate(row.cells):
                        t = cell.text_frame.text
                        if not t.strip():
                            continue
                        fpt = 8.0
                        for p in cell.text_frame.paragraphs:
                            for run in p.runs:
                                if run.font.size:
                                    fpt = run.font.size.pt
                        row_need = max(row_need,
                                       est_height_in(t, fpt, col_in[c], CELL_PAD_IN))
                    total_need += row_need
                h_in = sh.height / EMU_IN
                # a table may grow downward; compare against space to slide bottom
                avail = (prs.slide_height - sh.top) / EMU_IN - 0.55
                if total_need > avail:
                    problems.append(
                        (idx, sh.name[:26], f"table {len(tbl.rows)}r",
                         f"needs ~{total_need:.2f}in, {avail:.2f}in to footer",
                         total_need / avail))

    if not problems:
        print("PASS - no probable overflow detected")
        return 0

    problems.sort(key=lambda p: -p[-1])
    print(f"{len(problems)} probable overflow(s), worst first:\n")
    for idx, name, what, detail, ratio in problems:
        print(f"  slide {idx:>2}  {name:<28} {what:<22} {detail}  ({ratio:.2f}x)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1
                  else "RT-IIPF_Phase1_Review.pptx"))
