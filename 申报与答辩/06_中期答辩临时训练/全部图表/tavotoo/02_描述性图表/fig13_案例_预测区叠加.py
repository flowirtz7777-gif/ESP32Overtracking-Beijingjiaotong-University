"""Tavotto entry: existing results only; no training, no simulation.
existing_svg_vector_replay
"""
import sys
from pathlib import Path
LIBRARY=Path(__file__).resolve().parents[1]
SUPPORT=LIBRARY / "site-packages"
if str(SUPPORT) not in sys.path: sys.path.insert(0,str(SUPPORT))
from _support import draw

fig=draw('case_svg', 'fig13_案例_预测区叠加')
fig.savefig(Path(__file__).parent / 'fig13_案例_预测区叠加.pdf')
