"""M4 趋势增益精化。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

数据 D5（S4 联合精化，12 条选择轨迹 × 7 配置（g 0.375–1.25，含保持）× 8 条件 × 12 后处理变体，修正评分口径）。
研究问题：趋势增益细档与后处理的联合效果；保持方法加后处理后的表现。
注意：增益细档变化只出现在这 12 条选择轨迹上。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from common.config import DATA, DRIVE_CAT, DRIVE_NUM, METHOD_CAT, METHOD_NUM, OBS_NUM, POST_NUM  # noqa: E402
from common.modeling import Family, Task, by_group_kfold, estimate_units, leave_one, run_family  # noqa: E402
from common.monitor import run_main  # noqa: E402

df = pd.read_csv(DATA / "D5.csv")

TASKS = [
    Task("right_pct", label_dep="绝对值", key=True),
    Task("right_miss_rate", label_dep="绝对值"),
    Task("right_lead_p10_s", label_dep="绝对值"),
    Task("negative_fp_pct", label_dep="绝对值", key=True),
    Task("frame_fpr_pct", label_dep="绝对值"),
    Task("common_2s_fpr_pct", label_dep="绝对值"),
    Task("d_hold_right_pct", label_dep="配对差", exclude_hold=True, key=True),
    Task("d_hold_right_lead_p10_s", label_dep="配对差", exclude_hold=True),
    Task("d_hold_negative_fp_pct", label_dep="配对差", exclude_hold=True, key=True),
    Task("d_hold_common_2s_fpr_pct", label_dep="配对差", exclude_hold=True),
    Task("d_post_right_pct", label_dep="配对差"),
    Task("d_post_right_miss_rate", label_dep="配对差"),
    Task("d_post_negative_fp_pct", label_dep="配对差"),
    Task("d_post_common_2s_fpr_pct", label_dep="配对差"),
    Task("geom_2.0_mean", label_dep="标签无关", job_level=True),
    Task("geom_2.0_p95", label_dep="标签无关", job_level=True),
    Task("any_window_miss", kind="cls", label_dep="绝对值"),
    Task("any_no_before", kind="cls", label_dep="绝对值"),
    Task("fp_budget_pass", kind="cls", label_dep="绝对值"),
]

fam = Family(
    name="M4", title="趋势增益精化", out=Path(__file__).resolve().parent, train=df,
    num=DRIVE_NUM + METHOD_NUM + OBS_NUM + POST_NUM, cat=DRIVE_CAT + METHOD_CAT,
    tasks=TASKS,
    schemes={"按轨迹4折": by_group_kfold("case_id", 4), "留一动作模板": leave_one("template")},
    main_scheme="按轨迹4折",
    segments=["condition", "template", "v_B_mps", "config_id"],
    score_note="数据 S4 联合精化（修正评分口径），12 条选择轨迹（属于调参数据），增益细档效应只来自这 12 条轨迹。",
)

if __name__ == "__main__":
    sys.exit(run_main("M4", estimate_units(fam), lambda mon: run_family(fam, mon)))
