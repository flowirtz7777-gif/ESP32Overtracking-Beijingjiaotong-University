"""绘图共用设置：按 nature-figure skill（Python 后端）的出版规范。

- 字体 Arial，中文回落微软雅黑；SVG/PDF 文字可编辑（svg.fonttype=none、pdf.fonttype=42）。
- 只留左、下轴线；图例无边框；不画网格。
- 色板用 skill 的 PALETTE：蓝 = 主推方法，红 = 代价/对照，灰 = 参考。
- 导出 SVG（主）+ PDF + PNG（预览）；稠密散点请用 rasterized=True。
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# ---- skill PALETTE（references/api.md）----
PALETTE = {
    "blue_main": "#0F4D92", "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE", "green_2": "#AADCA9", "green_3": "#8BCF8B",
    "red_1": "#F6CFCB", "red_2": "#E9A6A1", "red_strong": "#B64342",
    "neutral_light": "#CFCECE", "neutral_mid": "#767676", "neutral_dark": "#4D4D4D", "neutral_black": "#272727",
    "gold": "#FFD700", "teal": "#42949E", "violet": "#9A4D8E", "magenta": "#EA84DD",
    "delta_up": "#2E9E44", "delta_down": "#E53935", "orange": "#E28E2C",
}
SEQ_CMAP = "magma"      # 连续量
DIV_CMAP = "RdBu_r"     # 有正负的变化量（红 = 更差/增加，蓝 = 更好/减少）


def apply_style(font_size: float = 8.0):
    plt.rcParams.update({
        "font.family": "sans-serif",
        # 中文图：微软雅黑放第一位（matplotlib 的 PDF/SVG 导出不做逐字回退，Arial 在前会缺中文字形）
        "font.sans-serif": ["Microsoft YaHei", "Arial", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": font_size,
        "axes.titlesize": font_size + 0.5,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size - 0.5,
        "ytick.labelsize": font_size - 0.5,
        "legend.fontsize": font_size - 0.5,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "axes.grid": False,
        "legend.frameon": False,
        "axes.unicode_minus": False,
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    })


apply_style()

TIER_COLOR = {"A": PALETTE["delta_up"], "B": PALETTE["orange"], "C": PALETTE["red_strong"]}
MODEL_COLOR = {"基线": PALETTE["neutral_light"], "Ridge": "#7884B4", "逻辑回归": "#7884B4",
               "随机森林": "#484878", "梯度提升": PALETTE["blue_main"]}
# 全项目统一的方法配色（skill：蓝 = 主推方法，红 = 基线，其余为强调色）
METHOD_COLOR = {"hold": PALETTE["red_strong"], "linear": PALETTE["teal"],
                "damped_linear": PALETTE["blue_main"], "bounded_second_order": PALETTE["violet"]}
METHOD_LABEL = {"hold": "保持", "linear": "线性", "damped_linear": "衰减线性", "bounded_second_order": "受限二阶"}
TEMPLATE_COLOR = {"symmetric": PALETTE["neutral_mid"], "fast_entry": PALETTE["blue_main"], "fast_return": PALETTE["orange"]}
TEMPLATE_LABEL = {"symmetric": "对称动作", "fast_entry": "较快入弯", "fast_return": "较快回正"}
QUAL = [PALETTE["blue_main"], PALETTE["red_strong"], PALETTE["teal"], PALETTE["violet"], PALETTE["orange"], PALETTE["neutral_mid"]]


def is_dark(rgba) -> bool:
    """背景色是否偏暗（用于决定格子里的文字用白色还是黑色）。"""
    r, g, b = rgba[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b < 0.5


def footnote(fig, text, y=-0.02):
    import textwrap
    width = max(60, int(fig.get_figwidth() * 13))  # 按图宽折行，避免长脚注把图撑宽
    fig.text(0.01, y, "\n".join(textwrap.wrap(text, width)), fontsize=6.5, color="#555555", ha="left", va="top")


def panel_label(ax, label, x=-0.08, y=1.04):
    """小写加粗面板标签，放在轴左上角外侧（skill add_panel_label）。"""
    ax.text(x, y, label, transform=ax.transAxes, fontsize=9, fontweight="bold", ha="left", va="bottom")


def save(fig, path, formats=("svg", "pdf", "png")):
    """SVG 为主，同时导出 PDF 与 PNG 预览；保存前去掉网格以符合出版规范。"""
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for ax in fig.axes:
        ax.grid(False)
    for fmt in formats:
        fig.savefig(path.with_suffix(f".{fmt}"))
    plt.close(fig)
