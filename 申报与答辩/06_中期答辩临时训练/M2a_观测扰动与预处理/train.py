"""M2a 观测扰动与预处理。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

数据 D2（S2，6 条代表轨迹 × 3 方法 × 16 观测条件 × 3 预处理，v3 评分口径）。
研究问题：噪声、延迟和简单预处理怎样改变端点误差、迟报与误报。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from common.config import DATA, DRIVE_CAT, DRIVE_NUM, METHOD_CAT, METHOD_NUM, OBS_NUM, PROC_CAT  # noqa: E402
from common.modeling import Family, Task, estimate_units, leave_one, run_family  # noqa: E402
from common.monitor import run_main  # noqa: E402

df = pd.read_csv(DATA / "D2.csv")
fam = Family(
    name="M2a", title="观测扰动与预处理", out=Path(__file__).resolve().parent, train=df,
    num=DRIVE_NUM + METHOD_NUM + OBS_NUM, cat=DRIVE_CAT + METHOD_CAT + PROC_CAT,
    tasks=[
        Task("geom_2.0_mean", label_dep="标签无关", job_level=True),
        Task("geom_2.0_p95", label_dep="标签无关", job_level=True, key=True),
        Task("right_pct", label_dep="绝对值"),
        Task("negative_fp_pct", label_dep="绝对值", key=True),
        Task("frame_fpr_pct", label_dep="绝对值"),
        Task("d_hold_right_pct", label_dep="配对差", exclude_hold=True, key=True),
        Task("d_hold_negative_fp_pct", label_dep="配对差", exclude_hold=True, key=True),
    ],
    schemes={"留一轨迹": leave_one("case_id")},
    main_scheme="留一轨迹",
    segments=["condition", "template", "v_B_mps", "config_id", "processor"],
    score_note="数据 S2（v3 评分口径），只有 6 条轨迹，结论稳健性有限。",
)

if __name__ == "__main__":
    sys.exit(run_main("M2a", estimate_units(fam), lambda mon: run_family(fam, mon)))
