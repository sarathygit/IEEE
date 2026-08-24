"""Render finguard.tex to a readable HTML preview.

This is a READING preview so the authors can review content without a LaTeX
toolchain. It is NOT camera-ready output -- the actual submission PDF must be
produced by compiling finguard.tex with IEEEtran (e.g. on Overleaf).

Handles the LaTeX subset actually used in the manuscript.
"""
import base64
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_NAME = sys.argv[1] if len(sys.argv) > 1 else "finguard.tex"
TEX = os.path.join(HERE, TEX_NAME)


def strip_comments(s):
    return "\n".join(l for l in s.split("\n") if not l.lstrip().startswith("%"))


def inline(s):
    """Inline markup -> HTML."""
    s = s.replace("\\%", "%").replace("\\&", "&amp;").replace("\\_", "_")
    s = re.sub(r"\\todo\{([^}]*)\}", r'<span class="todo">TODO: \1</span>', s)
    s = re.sub(r"\\textbf\{([^}]*)\}", r"<strong>\1</strong>", s)
    s = re.sub(r"\\emph\{([^}]*)\}", r"<em>\1</em>", s)
    s = re.sub(r"\\texttt\{([^}]*)\}", r"<code>\1</code>", s)
    s = re.sub(r"\\cite\{([^}]*)\}", r"[\1]", s)
    s = re.sub(r"\\ref\{(?:tab|fig|sec):([^}]*)\}", r"<em>\1</em>", s)
    s = re.sub(r"\\Sch\\\"?\{?o\}?lkopf", "Schölkopf", s)
    s = s.replace('\\"{o}', "ö").replace("\\'{e}", "é")
    # math-lite
    s = re.sub(r"\$\\approx\s*([^$]*)\$", r"≈\1", s)
    s = re.sub(r"\$\\tau\s*=\s*([^$]*)\$", r"τ=\1", s)
    s = re.sub(r"\$\\tau\$", "τ", s)
    s = re.sub(r"\$([\d.]+)\\times\$", r"\1×", s)
    s = re.sub(r"\$([\d.]+)\$", r"\1", s)
    s = re.sub(r"\$\\geq\$", "≥", s)
    s = re.sub(r"\$F_1\$", "F₁", s)
    s = re.sub(r"\$[^$]*\$", lambda m: m.group(0).strip("$")
               .replace("\\", "").replace("{", "").replace("}", ""), s)
    s = s.replace("---", "—").replace("--", "–")
    s = s.replace("``", "\u201c").replace("''", "\u201d")
    s = re.sub(r"\{,\}", ",", s)
    s = s.replace("~", " ").replace("\\ ", " ")
    s = re.sub(r"\\(vs|emph|textbf)\b", "", s)
    return s


def table_to_html(body, caption):
    rows = []
    for line in body.split("\\\\"):
        line = re.sub(r"\\(toprule|midrule|bottomrule|cmidrule)(\([^)]*\))?(\{[^}]*\})?",
                      "", line)
        line = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{([^}]*)\}", r"\1", line)
        line = line.strip()
        if not line:
            continue
        cells = [inline(c.strip()) for c in line.split("&")]
        rows.append(cells)
    if not rows:
        return ""
    head = "".join(f"<th>{c}</th>" for c in rows[0])
    body_html = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows[1:])
    return (f'<figure class="tbl"><figcaption>{inline(caption)}</figcaption>'
            f'<table><thead><tr>{head}</tr></thead><tbody>{body_html}'
            f"</tbody></table></figure>")


def img_data_uri(path):
    png = path.replace(".pdf", ".png")
    full = os.path.join(HERE, png)
    if not os.path.exists(full):
        return None
    with open(full, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def main():
    s = strip_comments(open(TEX).read())
    body = s.split("\\maketitle", 1)[1].split("\\end{document}")[0]

    title = re.search(r"\\title\{(.*?)\}\s*\n", s, re.S).group(1)
    title = " ".join(title.split())

    out = []

    # abstract
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.S)
    if m:
        out.append(f'<div class="abstract"><h3>Abstract</h3><p>'
                   f"{inline(' '.join(m.group(1).split()))}</p></div>")
        body = body.replace(m.group(0), "")

    m = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", body, re.S)
    if m:
        out.append(f'<p class="kw"><strong>Index terms—</strong>'
                   f"{inline(' '.join(m.group(1).split()))}</p>")
        body = body.replace(m.group(0), "")

    # tables
    for m in re.finditer(r"\\begin\{table\}.*?\\end\{table\}", body, re.S):
        blk = m.group(0)
        cap = re.search(r"\\caption\{(.*?)\}\s*\n", blk, re.S)
        tab = re.search(r"\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}", blk, re.S)
        html = table_to_html(tab.group(1), " ".join(cap.group(1).split())) if tab else ""
        body = body.replace(blk, "\n@@BLOCK@@" + html + "@@ENDBLOCK@@\n")

    # figures
    for m in re.finditer(r"\\begin\{figure\}.*?\\end\{figure\}", body, re.S):
        blk = m.group(0)
        cap = re.search(r"\\caption\{(.*?)\}\s*\n", blk, re.S)
        src = re.search(r"\\includegraphics\[[^\]]*\]\{([^}]*)\}", blk)
        html = ""
        if src:
            uri = img_data_uri(src.group(1))
            if uri:
                html = (f'<figure class="fig"><img src="{uri}" alt="figure">'
                        f'<figcaption>{inline(" ".join(cap.group(1).split()))}'
                        f"</figcaption></figure>")
        body = body.replace(blk, "\n@@BLOCK@@" + html + "@@ENDBLOCK@@\n")

    # bibliography
    m = re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", body, re.S)
    if m:
        items = re.split(r"\\bibitem\{[^}]*\}", m.group(0))[1:]
        lis = "".join(f"<li>{inline(' '.join(i.split()))}</li>"
                      for i in items if i.strip())
        body = body.replace(m.group(0),
                            "\n@@BLOCK@@<h2>References</h2><ol class='refs'>"
                            + lis + "</ol>@@ENDBLOCK@@\n")

    # walk remaining text
    for chunk in re.split(r"@@BLOCK@@(.*?)@@ENDBLOCK@@", body, flags=re.S):
        if chunk.strip().startswith("<"):
            out.append(chunk)
            continue
        for para in re.split(r"\n\s*\n", chunk):
            para = para.strip()
            if not para:
                continue
            para = re.sub(r"\\label\{[^}]*\}", "", para)
            sec = re.match(r"\\section\*?\{(.*?)\}(.*)", para, re.S)
            if sec:
                out.append(f"<h2>{inline(sec.group(1))}</h2>")
                para = sec.group(2).strip()
                if not para:
                    continue
            sub = re.match(r"\\subsection\*?\{(.*?)\}(.*)", para, re.S)
            if sub:
                out.append(f"<h3>{inline(sub.group(1))}</h3>")
                para = sub.group(2).strip()
                if not para:
                    continue
            if re.match(r"\\begin\{(itemize|enumerate)\}", para):
                tag = "ol" if "enumerate" in para[:20] else "ul"
                inner = re.sub(r"\\(begin|end)\{(itemize|enumerate)\}", "", para)
                lis = "".join(f"<li>{inline(' '.join(i.split()))}</li>"
                              for i in re.split(r"\\item", inner) if i.strip())
                out.append(f"<{tag}>{lis}</{tag}>")
                continue
            para = re.sub(r"\\(begin|end)\{[a-z*]+\}", "", para)
            if para.strip():
                out.append(f"<p>{inline(' '.join(para.split()))}</p>")

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<style>
@page {{ size: A4; margin: 18mm 20mm; }}
body {{ font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt;
       line-height: 1.55; color: #111; max-width: 46em; margin: 0 auto;
       padding: 24px; }}
.banner {{ background: #fff3cd; border: 1px solid #d9a400; padding: 10px 14px;
       font-family: system-ui, sans-serif; font-size: 9pt; margin-bottom: 22px; }}
h1 {{ font-size: 17pt; line-height: 1.3; text-align: center; margin: 0 0 6px; }}
.byline {{ text-align: center; font-family: system-ui, sans-serif;
       font-size: 9pt; color: #666; margin-bottom: 20px; }}
h2 {{ font-size: 12pt; margin: 22px 0 8px; border-bottom: 1px solid #ccc;
       padding-bottom: 3px; page-break-after: avoid; }}
h3 {{ font-size: 10.5pt; margin: 15px 0 5px; font-style: italic;
       page-break-after: avoid; }}
p {{ margin: 0 0 9px; text-align: justify; }}
.abstract {{ background: #f6f6f4; border-left: 3px solid #666; padding: 12px 16px;
       margin-bottom: 14px; font-size: 10pt; }}
.abstract h3 {{ margin: 0 0 6px; font-style: normal; font-weight: bold; }}
.kw {{ font-size: 9.5pt; color: #444; margin-bottom: 18px; }}
.todo {{ background: #ffe0e0; color: #b00; padding: 0 4px;
       font-family: system-ui, sans-serif; font-size: 9pt; font-weight: bold; }}
figure {{ margin: 16px 0; page-break-inside: avoid; }}
.fig img {{ width: 100%; max-width: 340px; display: block; margin: 0 auto; }}
figcaption {{ font-size: 8.5pt; color: #555; margin-top: 6px;
       font-family: system-ui, sans-serif; line-height: 1.4; }}
.tbl figcaption {{ margin: 0 0 6px; font-weight: bold; color: #222; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9pt;
       font-family: system-ui, sans-serif; }}
th {{ border-bottom: 1.5px solid #333; border-top: 1.5px solid #333;
       text-align: left; padding: 5px 7px; }}
td {{ border-bottom: 1px solid #ddd; padding: 4px 7px; }}
tbody tr:last-child td {{ border-bottom: 1.5px solid #333; }}
ol.refs {{ font-size: 9.5pt; }} ol.refs li {{ margin-bottom: 6px; }}
code {{ font-family: 'SF Mono', Menlo, monospace; font-size: 9pt;
       background: #f0f0ee; padding: 0 3px; }}
ul, ol {{ margin: 0 0 10px; padding-left: 22px; }} li {{ margin-bottom: 4px; }}
</style></head><body>
<div class="banner"><strong>READING PREVIEW — not the submission file.</strong>
The camera-ready PDF must be produced by compiling <code>finguard.tex</code>
with the IEEEtran class (e.g. on Overleaf). This preview exists so the content
can be reviewed without a LaTeX toolchain; layout, two-column formatting, and
page count will differ. Red markers show placeholders still to be filled.</div>
<h1>{title}</h1>
<div class="byline">Author block contains unfilled placeholders — see red markers</div>
{''.join(out)}
</body></html>"""

    dest = os.path.join(HERE, TEX_NAME.replace(".tex", "-preview.html"))
    open(dest, "w").write(html)
    print("wrote", dest)


if __name__ == "__main__":
    main()
