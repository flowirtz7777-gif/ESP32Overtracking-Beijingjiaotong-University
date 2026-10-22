"""P0：把 S1/S2 已有评分整理成分析表。

一行 = 一条轨迹 × 一个生效算法配置 × 一个观测条件 × 一种预处理。
- 工况特征从 datasets/<case>/profile.json 读取，不从文件名猜。
- 端点预测误差（标签无关）从各作业 summary.json 的 geometry 字段读取。
- 同一轨迹（S2 还要求同一观测条件与预处理）下与 hold 的配对差单独成列。

作者标记：Kiro。所有评分均为接触标签纠错前的 v3 结果。
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from common import DATASETS, JOBS, REPORTS, TABLES, ensure_dirs

SCORE_COLS = [
    "right_pct", "stratified_right_pct", "right_late", "right_miss", "right_no_before",
    "right_contacts", "right_lead_p10_s", "right_lead_median_s",
    "negative_fp_pct", "negative_fp", "negative_count",
    "frame_fpr_pct", "frame_recall_pct", "common_2s_reference_fpr_pct",
]
GEOM_COLS = [f"geom_{h}_{s}" for h in ("0.3", "1.0", "2.0") for s in ("mean", "p95", "max")]
PAIRED_TARGETS = [
    "right_pct", "negative_fp_pct", "frame_fpr_pct", "common_2s_reference_fpr_pct",
    "right_lead_p10_s", "geom_2.0_mean", "geom_2.0_p95",
]


def load_profile(case: str) -> dict:
    with open(DATASETS / case / "profile.json", encoding="utf-8") as fh:
        prof = json.load(fh)
    d = prof["design"]
    s = prof["summary"]
    return {
        "case_id": case,
        "v_B_mps": float(d["v_B_mps"]),
        "base_rate_deg_s": float(d["base_rate_deg_s"]),
        "entry_rate_deg_s": float(d["entry_rate_abs_deg_s"]),
        "return_rate_deg_s": float(d["return_rate_abs_deg_s"]),
        "template": d["template"],
        "alpha_peak_deg": float(d["alpha_peak_abs_deg"]),
        "duration_s": float(s["duration_s"]),
        "phi_max_deg": float(s["phi_max_deg"]),
    }


def load_geometry(job_id: str) -> dict:
    path = JOBS / job_id / "summary.json"
    out = {c: np.nan for c in GEOM_COLS}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as fh:
        summ = json.load(fh)
    if isinstance(summ, list):
        summ = summ[0]
    geo = summ.get("geometry", {})
    for h in ("0.3", "1.0", "2.0"):
        g = geo.get(h, {})
        out[f"geom_{h}_mean"] = g.get("mean_endpoint_error_m", np.nan)
        out[f"geom_{h}_p95"] = g.get("p95_endpoint_error_m", np.nan)
        out[f"geom_{h}_max"] = g.get("max_endpoint_error_m", np.nan)
    return out


def parse_condition(cond: str) -> dict:
    if cond == "clean":
        return {"noise_level": 0.0, "delay_ms": 0.0, "seed": 0}
    m = re.fullmatch(r"noise(\d{3})_s(\d)", cond)
    if m:
        return {"noise_level": int(m.group(1)) / 100, "delay_ms": 0.0, "seed": int(m.group(2))}
    m = re.fullmatch(r"delay(\d+)", cond)
    if m:
        return {"noise_level": 0.0, "delay_ms": float(m.group(1)), "seed": 0}
    m = re.fullmatch(r"combined(\d{3})_s(\d)", cond)
    if m:
        # 预登记定义：1 倍噪声叠加 100 ms 纯延迟
        return {"noise_level": int(m.group(1)) / 100, "delay_ms": 100.0, "seed": int(m.group(2))}
    raise ValueError(f"未知观测条件 {cond}")


def effective_params(row: pd.Series) -> dict:
    """只保留对该方法真正生效的参数；不适用的置 0，由 method 类别区分。"""
    m = row["method"]
    return {
        "gain_eff": float(row["gain"]) if m in ("linear", "damped_linear", "bounded_second_order") else 0.0,
        "decay_eff_s": float(row["decay_s"]) if m == "damped_linear" else 0.0,
        "accel_eff_s": float(row["acceleration_duration_s"]) if m == "bounded_second_order" else 0.0,
    }


def build(stage: str) -> pd.DataFrame:
    raw = pd.read_csv(REPORTS / f"{stage}_all_scores.csv")
    profiles = {c: load_profile(c) for c in raw["case_id"].unique()}
    rows = []
    for _, r in raw.iterrows():
        rec = {
            "stage": stage,
            "job_id": r["job_id"],
            "config_id": r["config_id"],
            "condition": r["condition"],
            "preprocessing": r["preprocessing"],
            "method": r["method"],
        }
        rec.update(profiles[r["case_id"]])
        rec.update(parse_condition(r["condition"]))
        rec.update(effective_params(r))
        rec.update({c: r[c] for c in SCORE_COLS})
        rec.update(load_geometry(r["job_id"]))
        rows.append(rec)
    df = pd.DataFrame(rows)

    # 与 hold 的配对差：同轨迹、同观测条件、同预处理
    key = ["case_id", "condition", "preprocessing"]
    hold = df[df["method"] == "hold"].set_index(key)[PAIRED_TARGETS]
    if hold.index.duplicated().any():
        raise RuntimeError("hold 基线在配对键上不唯一")
    joined = df.join(hold, on=key, rsuffix="__hold")
    for t in PAIRED_TARGETS:
        df[f"d_{t}"] = joined[t] - joined[f"{t}__hold"]
    return df


def coverage(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "trajectories": int(df["case_id"].nunique()),
        "configs": int(df["config_id"].nunique()),
        "conditions": sorted(df["condition"].unique().tolist()),
        "preprocessing": sorted(df["preprocessing"].unique().tolist()),
        "alpha_peak_deg_unique": sorted(df["alpha_peak_deg"].unique().tolist()),
        "geometry_missing_rows": int(df["geom_2.0_mean"].isna().sum()),
        "right_miss_total": int(df["right_miss"].sum()),
        "right_no_before_total": int(df["right_no_before"].sum()),
        "note": "right_miss / right_no_before 若全为 0，则不作为训练目标（无区分力）",
    }


def main():
    ensure_dirs()
    out = {}
    for stage in ("S1", "S2"):
        df = build(stage)
        df.to_csv(TABLES / f"{stage.lower()}_rows.csv", index=False, encoding="utf-8-sig")
        out[stage] = coverage(df)
        print(stage, json.dumps(out[stage], ensure_ascii=False))
    with open(TABLES / "dataset_coverage.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
