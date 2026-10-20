# -*- coding: utf-8 -*-
"""把《第四部分_盲区驭智产品与技术解决方案.md》转换为 LaTeX 并保留结构。"""
from __future__ import annotations

import re
from pathlib import Path

MD_GLOB = "第四部分*.md"
SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = SCRIPT_DIR / "源文件"


def find_md() -> Path:
    hits = sorted(SOURCE_DIR.glob(MD_GLOB))
    if not hits:
        raise SystemExit("未找到第四部分 md 文件")
    return hits[0]


def escape_latex(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append(r"\textbackslash{}")
        elif ch in "{}$&%#_~^":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def post_specials(s: str) -> str:
    """在转义之后替换特殊符号（此时插入的 LaTeX 命令不会再被转义）。"""
    return s.replace("\u2212", "-").replace("\u2264", r"$\le$").replace("\u00d7", r"$\times$")


def text_inline(s: str) -> str:
    """处理一段正文文本：代码片段、加粗、特殊字符、LaTeX 转义。"""
    tokens = []
    pos = 0
    pattern = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*)")
    for m in pattern.finditer(s):
        tokens.append(post_specials(escape_latex(s[pos:m.start()])))
        token = m.group(0)
        if token.startswith("`"):
            tokens.append(r"\texttt{" + escape_latex(token[1:-1].replace("\u2212", "-")) + "}")
        else:
            tokens.append(r"\textbf{" + post_specials(escape_latex(token[2:-2])) + "}")
        pos = m.end()
    tokens.append(post_specials(escape_latex(s[pos:])))
    return "".join(tokens)


def table_spec(header: str) -> str:
    if "参数" in header:
        return "p{3.2cm}p{7.4cm}p{2.6cm}"
    if "判定条件" in header:
        return "p{5.6cm}p{2.2cm}p{3.2cm}"
    if "阶段" in header:
        return "p{2.2cm}p{7.4cm}p{4.2cm}"
    return "l l l"


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render_table(rows: list[str]) -> list[str]:
    header = split_row(rows[0])
    data = [split_row(r) for r in rows[2:]]
    spec = table_spec(header[0] if header else "")
    out = ["\\begin{center}", "\\small", "\\begin{tabular}{" + spec + "}", "\\hline"]
    out.append(" & ".join(r"\textbf{" + escape_latex(c) + "}" for c in header) + r" \\")
    out.append("\\hline")
    for row in data:
        out.append(" & ".join(text_inline(c) for c in row) + r" \\")
        out.append("\\hline")
    out.append("\\end{tabular}")
    out.append("\\end{center}")
    return out


def main() -> None:
    md = find_md()
    lines = md.read_text(encoding="utf-8").splitlines()
    tex_name = md.with_suffix(".tex")

    out: list[str] = [
        r"\documentclass[UTF8,11pt]{ctexart}",
        r"\usepackage[a4paper,top=2.6cm,bottom=2.6cm,left=2.8cm,right=2.8cm]{geometry}",
        r"\usepackage{array}",
        r"\usepackage{amsmath}",
        r"\usepackage{xcolor}",
        r"\setmainfont{Times New Roman}",
        r"\setCJKmainfont[BoldFont=SimHei]{SimSun}",
        r"\setmonofont{SimSun}",
        r"\setlength{\parskip}{3pt}",
        r"\begin{document}",
    ]

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("$$"):
            math = stripped[2:-2].strip()
            math = re.sub(r"\\tag\{[^}]*\}", "", math)
            out.append(r"\begin{equation}")
            out.append(math)
            out.append(r"\end{equation}")
            i += 1
            continue

        if stripped.startswith("```"):
            i += 1
            code: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i].replace("\u2212", "-"))
                i += 1
            out.append("\\begin{verbatim}")
            out.extend(code)
            out.append("\\end{verbatim}")
            i += 1
            continue

        if stripped.startswith("|"):
            rows = [line]
            i += 1
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].rstrip())
                i += 1
            out.extend(render_table(rows))
            continue

        if stripped.startswith("#### "):
            out.append(r"\subsubsection*{" + text_inline(stripped[5:]) + "}")
            i += 1
            continue
        if stripped.startswith("### "):
            out.append(r"\subsection*{" + text_inline(stripped[4:]) + "}")
            i += 1
            continue
        if stripped.startswith("## "):
            out.append(r"\section*{" + text_inline(stripped[3:]) + "}")
            i += 1
            continue
        if stripped.startswith("# "):
            out.append(r"\section*{\Large " + text_inline(stripped[2:]) + "}")
            i += 1
            continue

        if stripped.startswith("> "):
            quote: list[str] = []
            while i < n and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:])
                i += 1
            out.append("\\begin{quote}\\small")
            out.append(text_inline(" ".join(quote)))
            out.append("\\end{quote}")
            continue

        if stripped == "":
            i += 1
            continue

        para: list[str] = []
        while i < n and lines[i].strip() != "":
            para.append(lines[i].rstrip())
            i += 1
        out.append(text_inline(" ".join(p.strip() for p in para)))
        out.append("")

    out.append(r"\end{document}")
    tex_name.write_text("\n".join(out), encoding="utf-8")
    print("TEX_SAVED:", tex_name.resolve())


if __name__ == "__main__":
    main()
