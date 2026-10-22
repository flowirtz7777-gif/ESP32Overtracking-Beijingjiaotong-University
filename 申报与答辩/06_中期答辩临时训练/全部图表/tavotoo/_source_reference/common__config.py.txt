"""中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

共用路径、随机种子、临时模型表现分档阈值与特征白名单。作者标记：Kiro，2026-10-22。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

# Z 盘权威实验结果（只读）
ZROOT = Path(r"Z:\大创内轮差项目_实验结果\科研实验_2026-10-14")
RUNS = ZROOT / "runs"
V3 = RUNS / "overnight_20261014_v3"
AFT = RUNS / "afternoon_S4_v1"
DATASETS = ZROOT / "datasets"

SOURCES = {
    "D1_S1": V3 / "reports" / "S1_all_scores.csv",
    "D2_S2": V3 / "reports" / "S2_all_scores.csv",
    "D3_S3": AFT / "reports" / "S3_consistent_scoring_scores.csv",
    "D4_S4proc": AFT / "reports" / "S4_processor_scores.csv",
    "D5_S4joint": AFT / "reports" / "S4_joint_scores.csv",
}
JOB_DIRS = [AFT / "jobs", V3 / "jobs"]
DEEPSEEK_BOUNDS = REPO / "申报与答辩" / "04_中期答辩_DeepSeek" / "midterm_paired_bounds.csv"

DATA = ROOT / "P0_数据整理" / "data"
LOGS = ROOT / "logs"

SEED = 20261022
N_PERM_REPEATS = 5

# 临时模型表现分档阈值（执行前冻结，见 PLAN.md 第 7 节；只衡量对纠错前评分的预测能力，非科研准入）
TIER_A = {"skill": 0.30, "r2": 0.50, "auc": 0.75}
SAFETY_RECALL = 0.90  # “安全优先”分类阈值：在开发集折外预测上至少抓住 90% 正例

# 输入白名单
DRIVE_NUM = ["v_B_mps", "entry_rate_deg_s", "return_rate_deg_s"]
DRIVE_CAT = ["template"]
METHOD_NUM = ["gain_eff", "decay_eff_s", "accel_eff_s"]
METHOD_CAT = ["method"]
OBS_NUM = ["noise_level", "delay_ms"]
PROC_CAT = ["processor"]
POST_NUM = ["EXIT_W_s", "margin_m", "confirmation_s"]

FEATURE_GROUPS = {
    "转向动作": ["entry_rate_deg_s", "return_rate_deg_s", "template"],
    "方法及参数": ["method", "gain_eff", "decay_eff_s", "accel_eff_s"],
    "观测扰动": ["noise_level", "delay_ms"],
    "后处理": ["EXIT_W_s", "margin_m", "confirmation_s"],
}

FEATURE_LABEL = {
    "v_B_mps": "车速 v_B", "entry_rate_deg_s": "入弯转角速率", "return_rate_deg_s": "回正转角速率",
    "template": "动作模板", "method": "预测方法", "gain_eff": "趋势增益 g", "decay_eff_s": "衰减时间 τ",
    "accel_eff_s": "二阶生效时长", "noise_level": "噪声倍率", "delay_ms": "纯延迟",
    "processor": "输入处理", "EXIT_W_s": "出弯窗口 W", "margin_m": "空间膨胀", "confirmation_s": "确认时间",
}

TARGET_LABEL = {
    "geom_0.3_mean": "0.3 s 端点误差均值 (m)", "geom_1.0_mean": "1 s 端点误差均值 (m)",
    "geom_2.0_mean": "2 s 端点误差均值 (m)", "geom_2.0_p95": "2 s 端点误差 P95 (m)",
    "right_pct": "RIGHT 不足率 (%)", "right_miss_rate": "窗口漏报率 (%)",
    "right_lead_p10_s": "提前量 P10 (s)", "negative_fp_pct": "近场点误报率 (%)",
    "frame_fpr_pct": "逐帧误报率 (%)", "common_2s_fpr_pct": "共同 2 s 逐帧误报率 (%)",
    "any_window_miss": "出现窗口漏报", "any_no_before": "接触前完全无报警", "fp_budget_pass": "误报预算达标",
}


def target_label(name: str) -> str:
    refs = {"d_hold_": "保持", "d_post_": "无后处理", "d_raw_": "raw"}
    for prefix, ref in refs.items():
        if name.startswith(prefix):
            base = TARGET_LABEL.get(name[len(prefix):], name[len(prefix):])
            text, _, unit = base.partition(" (")
            unit = unit.rstrip(")")
            unit = "pp" if unit == "%" else unit
            return f"{text} − {ref} ({unit})" if unit else f"{text} − {ref}"
    return TARGET_LABEL.get(name, name)


HEADER = "中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。"
