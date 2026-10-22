"""A 线中期分析的共用路径、特征定义与绘图设置。

作者标记：Kiro。只读使用 v3 已有评分（纠错前），不修改任何冻结数据。
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESEARCH = REPO / "工具" / "转弯全过程盲区分析软件" / "科研实验_2026-10-14"
REPORTS = RESEARCH / "reports"
JOBS = RESEARCH / "runs" / "overnight_20261014_v3" / "jobs"
DATASETS = RESEARCH / "datasets" / "development_v2_n70000"
# DeepSeek 正向区间评分结果（已随分支提交）
DEEPSEEK_BOUNDS = REPO / "申报与答辩" / "04_中期答辩_DeepSeek" / "midterm_paired_bounds.csv"

OUT = HERE / "outputs"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"

SEED = 20261022

# 工况特征：只用可在线获得 / 实验设计可控的量，不用 case_id、种子、接触时间、已有评分
DRIVE_NUMERIC = ["v_B_mps", "entry_rate_deg_s", "return_rate_deg_s"]
DRIVE_CATEGORICAL = ["template"]
# 算法特征：方法类别 + 方法专属的实际生效参数（不适用时置 0，并由方法类别区分）
METHOD_NUMERIC = ["gain_eff", "decay_eff_s", "accel_eff_s"]
METHOD_CATEGORICAL = ["method"]
# 观测特征（仅 S2）
OBS_NUMERIC = ["noise_level", "delay_ms"]
OBS_CATEGORICAL = ["preprocessing"]

METHOD_LABEL = {
    "hold": "保持",
    "linear": "线性",
    "damped_linear": "衰减线性",
    "bounded_second_order": "受限二阶",
}

FEATURE_LABEL = {
    "v_B_mps": "车速 v_B",
    "entry_rate_deg_s": "入弯转角速率",
    "return_rate_deg_s": "回正转角速率",
    "template": "动作模板",
    "method": "预测方法",
    "gain_eff": "线性增益 g",
    "decay_eff_s": "衰减时间 τ",
    "accel_eff_s": "二阶生效时长",
    "noise_level": "噪声倍率",
    "delay_ms": "纯延迟",
    "preprocessing": "预处理",
}


def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 110
    plt.rcParams["savefig.dpi"] = 200
    plt.rcParams["savefig.bbox"] = "tight"
    return plt


def ensure_dirs():
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
