"""按步骤名启动脚本（供 run_all.ps1 使用，避免在 PowerShell 脚本里写中文路径）。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = {
    "P0": ROOT / "P0_数据整理" / "build_all.py",
    "M1": ROOT / "M1_核心预测方法" / "train.py",
    "M2a": ROOT / "M2a_观测扰动与预处理" / "train.py",
    "M2b": ROOT / "M2b_状态估计筛选" / "train.py",
    "M3": ROOT / "M3_二级处理联合" / "train.py",
    "M4": ROOT / "M4_趋势增益精化" / "train.py",
    "SUM": ROOT / "汇总" / "summarize.py",
}

if __name__ == "__main__":
    step = sys.argv[1]
    sys.argv = [str(STEPS[step])]
    runpy.run_path(str(STEPS[step]), run_name="__main__")
