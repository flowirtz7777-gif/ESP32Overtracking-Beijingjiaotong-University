"""M1 核心预测方法。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

数据 D1（S1，27 条开发轨迹 × 19 个配置，clean，v3 评分口径）。
研究问题：预测方法和外推参数在不同驾驶工况下的端点误差与迟报。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from common.config import DATA, DRIVE_CAT, DRIVE_NUM, METHOD_CAT, METHOD_NUM  # noqa: E402
from common.modeling import Family, Task, by_group_kfold, estimate_units, leave_one, run_family  # noqa: E402
from common.monitor import run_main  # noqa: E402

df = pd.read_csv(DATA / "D1.csv")
fam = Family(
    name="M1", title="核心预测方法", out=Path(__file__).resolve().parent, train=df,
    num=DRIVE_NUM + METHOD_NUM, cat=DRIVE_CAT + METHOD_CAT,
    tasks=[
        Task("geom_0.3_mean", label_dep="标签无关"),
        Task("geom_1.0_mean", label_dep="标签无关"),
        Task("geom_2.0_mean", label_dep="标签无关", key=True),
        Task("geom_2.0_p95", label_dep="标签无关"),
        Task("d_hold_right_pct", label_dep="配对差", exclude_hold=True, key=True),
        Task("d_hold_right_lead_p10_s", label_dep="配对差", exclude_hold=True),
        Task("d_hold_negative_fp_pct", label_dep="配对差", exclude_hold=True, key=True),
        Task("right_pct", label_dep="绝对值", key=True),
        Task("negative_fp_pct", label_dep="绝对值"),
    ],
    schemes={"按轨迹5折": by_group_kfold("case_id", 5), "留一动作模板": leave_one("template")},
    main_scheme="按轨迹5折",
    segments=["template", "v_B_mps", "config_id"],
    score_note="数据 S1（v3 评分口径，误报类数值略高于修正口径），27 条轨迹，转角峰值均为 10°。",
)

if __name__ == "__main__":
    sys.exit(run_main("M1", estimate_units(fam), lambda mon: run_family(fam, mon)))
