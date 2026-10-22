"""Tavotto entry: existing results only; no training, no simulation.
existing_summary_table
"""
import sys
from pathlib import Path
LIBRARY=Path(__file__).resolve().parents[1]
SUPPORT=LIBRARY / "site-packages"
if str(SUPPORT) not in sys.path: sys.path.insert(0,str(SUPPORT))
from _support import draw

fig=draw('summary', 'fig11_全部模型临时表现分档总图')
fig.savefig(Path(__file__).parent / 'fig11_全部模型临时表现分档总图.pdf')
