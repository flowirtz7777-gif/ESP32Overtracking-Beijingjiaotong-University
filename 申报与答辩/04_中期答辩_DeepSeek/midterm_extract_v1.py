"""Extract midterm results from the batch record into a paper-ready table.

Reads only the JSON produced by midterm_batch_driver_v1.py. Emits:
  * markdown table of A/B/paired RIGHT-insufficiency bounds per condition
  * a compact CSV
  * a machine-readable summary with the interval width of each paired bound

AUTHOR MARKER: DeepSeek (AI assistant). Midterm-support artefact.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
RECORD = os.path.join(HERE, "midterm_batch_v1", "midterm_batch_record_v1.json")


def pct(record):
    if not record or record.get("lower") is None:
        return None
    lo = Fraction(record["lower"]["numerator"], record["lower"]["denominator"])
    hi = Fraction(record["upper"]["numerator"], record["upper"]["denominator"])
    return float(lo * 100), float(hi * 100)


def main():
    if not os.path.exists(RECORD):
        raise SystemExit(f"batch record not found: {RECORD}")
    record = json.load(open(RECORD, encoding="utf-8"))
    rows = []
    for pair in record.get("pairs", []):
        if "error" in pair:
            rows.append({"condition": pair.get("condition", "?"),
                         "method_A": pair.get("method_A", "?"),
                         "error": pair["error"]})
            continue
        bounds = pair["right_insufficient_bound"]
        a = pct(bounds["A"])
        b = pct(bounds["B"])
        d = pct(bounds["paired_A_minus_B"])
        rows.append({
            "condition": pair["condition"],
            "method_A": pair["method_A"],
            "A_right_pct": f"{a[0]:.3f}..{a[1]:.3f}" if a else "undefined",
            "B_hold_pct": f"{b[0]:.3f}..{b[1]:.3f}" if b else "undefined",
            "paired_pct": f"{d[0]:+.3f}..{d[1]:+.3f}" if d else "undefined",
            "paired_width_pp": round(d[1] - d[0], 4) if d else None,
            "A_strictly_better": bool(d and d[1] < 0),
            "B_strictly_better": bool(d and d[0] > 0),
            "covers_zero": bool(d and d[0] <= 0 <= d[1]),
            "score_seconds": pair.get("score_seconds"),
        })

    base = os.path.join(HERE, "midterm_batch_v1")
    os.makedirs(base, exist_ok=True)
    csv_path = os.path.join(base, "midterm_paired_bounds.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["condition"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    lines = ["# 中期答辩：A/B RIGHT 不足率配对区间（正向评分，独立核验延后）", "",
             "| 观测条件 | 对比方法 A | A 不足率% | B=hold 不足率% | 配对差 A−B (pp) | 区间宽 | A 更优 | 跨零 |",
             "|---|---|---|---|---|---:|:---:|:---:|"]
    for row in rows:
        if "error" in row:
            lines.append(f"| {row['condition']} | {row['method_A']} | — | — | 失败: {row['error'][:40]} | — | — | — |")
            continue
        lines.append(
            f"| {row['condition']} | {row['method_A']} | {row['A_right_pct']} | "
            f"{row['B_hold_pct']} | {row['paired_pct']} | {row['paired_width_pp']} | "
            f"{'是' if row['A_strictly_better'] else ''} | {'是' if row['covers_zero'] else ''} |"
        )
    lines += ["",
              "说明：正向评分（numpy 路径），独立有理数核验按人类指令延后，",
              "结果仅用于中期答辩展示，不构成 ranking / training 准入。",
              "作者：DeepSeek"]
    md_path = os.path.join(base, "midterm_paired_bounds.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    summary = {
        "conditions": len({r.get("condition") for r in rows}),
        "pairs": len(rows),
        "errors": sum(1 for r in rows if "error" in r),
        "A_strictly_better_count": sum(1 for r in rows if r.get("A_strictly_better")),
        "covers_zero_count": sum(1 for r in rows if r.get("covers_zero")),
        "csv": csv_path,
        "markdown": md_path,
        "forward_only": True,
        "independent_close_deferred": True,
    }
    print(json.dumps(summary, ensure_ascii=False))
    print(open(md_path, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
