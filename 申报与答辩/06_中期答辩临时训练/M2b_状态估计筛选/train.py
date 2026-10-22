"""M2b 状态估计筛选。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

数据 D4（S4 状态估计筛选，6 条轨迹 × 3 方法 × 8 条件 × 4 种输入处理，修正评分口径）。
研究问题：φ 滤波与转角低通能否降低误报，代价（迟报、漏报）多大。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from common.config import DATA, DRIVE_CAT, DRIVE_NUM, METHOD_CAT, METHOD_NUM, OBS_NUM, PROC_CAT  # noqa: E402
from common.modeling import Family, Task, estimate_units, leave_one, run_family  # noqa: E402
from common.monitor import run_main  # noqa: E402

df = pd.read_csv(DATA / "D4.csv")
fam = Family(
    name="M2b", title="状态估计筛选", out=Path(__file__).resolve().parent, train=df,
    num=DRIVE_NUM + METHOD_NUM + OBS_NUM, cat=DRIVE_CAT + METHOD_CAT + PROC_CAT,
    tasks=[
        Task("geom_2.0_mean", label_dep="标签无关", job_level=True),
        Task("geom_2.0_p95", label_dep="标签无关", job_level=True),
        Task("right_pct", label_dep="绝对值"),
        Task("right_miss_rate", label_dep="绝对值", key=True),
        Task("negative_fp_pct", label_dep="绝对值", key=True),
        Task("frame_fpr_pct", label_dep="绝对值"),
        Task("d_hold_right_pct", label_dep="配对差", exclude_hold=True),
        Task("d_raw_right_pct", label_dep="配对差", key=True),
        Task("d_raw_right_miss_rate", label_dep="配对差"),
        Task("d_raw_negative_fp_pct", label_dep="配对差", key=True),
    ],
    schemes={"留一轨迹": leave_one("case_id")},
    main_scheme="留一轨迹",
    segments=["condition", "template", "v_B_mps", "config_id", "processor"],
    score_note="数据 S4 状态估计筛选（修正评分口径），只有 6 条轨迹，结论稳健性有限。",
)

if __name__ == "__main__":
    sys.exit(run_main("M2b", estimate_units(fam), lambda mon: run_family(fam, mon)))
