from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from common import ROOT, read_json, write_json


def csv_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for r in rows for k in r if not isinstance(r[k], (dict, list))})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows({k: r.get(k) for k in fields} for r in rows)


def statistics(rows):
    if not rows:
        return None
    return {"folds": len(rows), "right_miss_sum": sum(r["right_miss"] for r in rows),
        "right_no_before_sum": sum(r["right_no_before"] for r in rows),
        "worst_right_pct": max(r["right_pct"] for r in rows),
        "worst_stratified_right_pct": max(r["stratified_right_pct"] for r in rows),
        "mean_right_pct": float(np.mean([r["right_pct"] for r in rows])),
        "worst_point_fp_pct": max(r["negative_fp_pct"] for r in rows),
        "worst_frame_fpr_pct": max(r["frame_fpr_pct"] for r in rows),
        "worst_2s_reference_fpr_pct": max(r["common_2s_reference_fpr_pct"] for r in rows),
        "passes_research_budget": all(r["right_miss"]==0 and r["right_no_before"]==0 and
                                      r["negative_fp_pct"]<=5 and r["frame_fpr_pct"]<=.5 for r in rows)}


def rank_key(s):
    return (0 if s["right_miss_sum"]==0 and s["right_no_before_sum"]==0 else 1,
            0 if s["worst_point_fp_pct"]<=5 and s["worst_frame_fpr_pct"]<=.5 else 1,
            s["right_miss_sum"], s["right_no_before_sum"], s["worst_stratified_right_pct"], s["worst_point_fp_pct"])


def core_report(rows, configs):
    grouped = []
    for config_id, method in configs.items():
        a = [r for r in rows if r["config_id"]==config_id]
        if a:
            grouped.append({"config_id": config_id, "method": method, **statistics(a)})
    grouped.sort(key=rank_key)
    families = []
    for mode in ["hold", "linear", "damped_linear", "bounded_second_order"]:
        family = [r for r in grouped if r["method"]["mode"]==mode]
        if family:
            families.append(family[0])
    families.sort(key=rank_key)
    finalists = families[:2]
    report = {"status": "completed", "configurations": grouped, "family_best": families,
              "finalists": finalists, "physical_validation": False,
              "independent_final_test": False, "no_feasible_configuration": not any(s["passes_research_budget"] for s in grouped)}
    write_json(ROOT/"reports"/"S1_analysis.json", report)
    csv_rows(ROOT/"reports"/"S1_all_scores.csv", rows)
    csv_rows(ROOT/"reports"/"S1_configuration_comparison.csv", grouped)
    lines = ["# S1核心方法与驾驶因素结果", "", f"完成{len(rows)}个方法/轨迹评分。每条轨迹的所有方法使用同一冻结目标集。",
             "", "| 配置 | 方法 | 最坏RIGHT不足% | 窗口漏报实例 | 最坏点误报% | 研究门槛通过 |",
             "| --- | --- | ---: | ---: | ---: | --- |"]
    for s in grouped:
        lines.append(f"| {s['config_id']} | {s['method']['mode']} | {s['worst_right_pct']:.3f} | {s['right_miss_sum']} | {s['worst_point_fp_pct']:.3f} | {s['passes_research_budget']} |")
    lines += ["", "下一阶段保留两种方法及独立保持基线。没有同时通过漏报与误报预算时，排名仅为探索性排序。",
              "连续帧、目标点和噪声种子不是独立车辆试验。几何评分与报警处理均为仿真结果。", ""]
    (ROOT/"reports"/"S1核心方法结果.md").write_text("\n".join(lines), encoding="utf-8")
    return report
