"""Tavotto entry: existing results only; no training, no simulation.
original_plot_code
"""
import sys
from pathlib import Path
LIBRARY=Path(__file__).resolve().parents[1]
SUPPORT=LIBRARY / "site-packages"
if str(SUPPORT) not in sys.path: sys.path.insert(0,str(SUPPORT))
from _support import draw

fig=draw('M1_核心预测方法', 'fig04_分段误差')
fig.savefig(Path(__file__).parent / 'M1__fig04_分段误差.pdf')
