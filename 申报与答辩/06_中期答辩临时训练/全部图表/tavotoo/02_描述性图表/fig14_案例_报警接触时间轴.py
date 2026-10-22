"""Tavotto entry: existing results only; no training, no simulation.
existing_svg_vector_replay
"""
import sys
from pathlib import Path
LIBRARY=Path(__file__).resolve().parents[1]
SUPPORT=LIBRARY / "site-packages"
if str(SUPPORT) not in sys.path: sys.path.insert(0,str(SUPPORT))
from _support import draw

fig=draw('case_svg', 'fig14_案例_报警接触时间轴')
fig.savefig(Path(__file__).parent / 'fig14_案例_报警接触时间轴.pdf')
