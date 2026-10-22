"""可复现记录：源文件、代码与依赖版本的哈希绑定。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
"""
from __future__ import annotations

import hashlib
import platform
import sys
import time
from pathlib import Path

from .config import ROOT, SEED


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def aggregate(hashes: dict) -> str:
    """把 {路径: sha256} 按路径排序后再求一次 SHA256，作为整组文件的指纹。"""
    h = hashlib.sha256()
    for k in sorted(hashes):
        h.update(f"{k}\t{hashes[k]}\n".encode("utf-8"))
    return h.hexdigest()


def code_hashes() -> dict:
    files = sorted(p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts)
    files += [ROOT / "run_all.ps1"]
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in files if p.exists()}


def environment() -> dict:
    import matplotlib
    import numpy
    import pandas
    import scipy
    import sklearn
    import joblib
    return {"python": sys.version.split()[0], "platform": platform.platform(), "numpy": numpy.__version__,
            "pandas": pandas.__version__, "scipy": scipy.__version__, "scikit-learn": sklearn.__version__,
            "matplotlib": matplotlib.__version__, "joblib": joblib.__version__, "seed": SEED}


def run_record(extra: dict | None = None) -> dict:
    code = code_hashes()
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "environment": environment(),
           "code_sha256": code, "code_aggregate_sha256": aggregate(code)}
    if extra:
        rec.update(extra)
    return rec
