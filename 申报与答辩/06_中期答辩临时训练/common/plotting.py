"""绘图共用设置。"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 110
plt.rcParams["savefig.dpi"] = 170
plt.rcParams["savefig.bbox"] = "tight"

TIER_COLOR = {"A": "#2ca02c", "B": "#ff7f0e", "C": "#d62728"}
MODEL_COLOR = {"基线": "#bbbbbb", "Ridge": "#9467bd", "逻辑回归": "#9467bd", "随机森林": "#8c564b", "梯度提升": "#17becf"}
METHOD_COLOR = {"hold": "#7f7f7f", "linear": "#1f77b4", "damped_linear": "#2ca02c", "bounded_second_order": "#d62728"}
METHOD_LABEL = {"hold": "保持", "linear": "线性", "damped_linear": "衰减线性", "bounded_second_order": "受限二阶"}


def footnote(fig, text, y=-0.02):
    fig.text(0.01, y, text, fontsize=8, color="#555555", ha="left", va="top")


def save(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
