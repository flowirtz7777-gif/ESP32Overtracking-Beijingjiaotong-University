"""M3 二级处理联合（主模型）。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

训练：D3 开发集（27 条轨迹 × 2 方法 × 8 条件 × 12 后处理变体 + 保持基线，修正评分口径）。
外部检验：D3 选择集（12 条中间档车速/速率轨迹），模型定型后只评一次。
研究问题：出弯扩窗、空间膨胀、确认时间与工况、噪声的交互；能否预测“会不会漏报”。
主方案内对随机森林、梯度提升做小网格调参（内层按轨迹 3 折，嵌套）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from common.config import DATA, DRIVE_CAT, DRIVE_NUM, METHOD_CAT, METHOD_NUM, OBS_NUM, POST_NUM  # noqa: E402
from common.modeling import Family, Task, by_group_kfold, estimate_units, leave_one, run_family  # noqa: E402
from common.monitor import run_main  # noqa: E402

d3 = pd.read_csv(DATA / "D3.csv")
dev = d3[d3.partition == "development_v2_n70000"].reset_index(drop=True)
sel = d3[d3.partition == "selection_v2"].reset_index(drop=True)

TASKS = [
    Task("right_pct", label_dep="绝对值", key=True),
    Task("right_miss_rate", label_dep="绝对值"),
    Task("right_lead_p10_s", label_dep="绝对值"),
    Task("negative_fp_pct", label_dep="绝对值", key=True),
    Task("frame_fpr_pct", label_dep="绝对值"),
    Task("common_2s_fpr_pct", label_dep="绝对值"),
    Task("d_hold_right_pct", label_dep="配对差", exclude_hold=True),
    Task("d_hold_right_lead_p10_s", label_dep="配对差", exclude_hold=True),
    Task("d_hold_negative_fp_pct", label_dep="配对差", exclude_hold=True),
    Task("d_hold_common_2s_fpr_pct", label_dep="配对差", exclude_hold=True),
    Task("d_post_right_pct", label_dep="配对差", exclude_hold=True, key=True),
    Task("d_post_right_miss_rate", label_dep="配对差", exclude_hold=True),
    Task("d_post_negative_fp_pct", label_dep="配对差", exclude_hold=True, key=True),
    Task("d_post_common_2s_fpr_pct", label_dep="配对差", exclude_hold=True),
    Task("geom_2.0_mean", label_dep="标签无关", job_level=True),
    Task("geom_2.0_p95", label_dep="标签无关", job_level=True),
    Task("any_window_miss", kind="cls", label_dep="绝对值", key=True),
    Task("any_no_before", kind="cls", label_dep="绝对值", key=True),
    Task("fp_budget_pass", kind="cls", label_dep="绝对值", key=True),
]

fam = Family(
    name="M3", title="二级处理联合（主模型）", out=Path(__file__).resolve().parent, train=dev, external=sel,
    num=DRIVE_NUM + METHOD_NUM + OBS_NUM + POST_NUM, cat=DRIVE_CAT + METHOD_CAT,
    tasks=TASKS,
    schemes={"按轨迹5折": by_group_kfold("case_id", 5), "留一动作模板": leave_one("template"),
             "留一观测族": leave_one("obs_family")},
    main_scheme="按轨迹5折", tune=True,
    learning_curve=["right_pct", "negative_fp_pct", "d_post_negative_fp_pct", "any_window_miss"],
    pdp_features=["EXIT_W_s", "margin_m", "confirmation_s", "noise_level"],
    segments=["condition", "template", "v_B_mps", "config_id"],
    score_note="数据 S3（修正评分口径），训练 27 条开发轨迹，外部检验 12 条选择轨迹，转角峰值均为 10°。",
)

if __name__ == "__main__":
    sys.exit(run_main("M3", estimate_units(fam), lambda mon: run_family(fam, mon)))
