"""独立进程加载已保存的模型，用原始字段样例重新预测并与训练时的预测比对。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
rows = []
for model_path in sorted(ROOT.glob("M*/model/*.joblib")):
    task = model_path.stem
    schema = json.loads((model_path.parent / f"{task}__schema.json").read_text(encoding="utf-8"))
    sample = pd.read_csv(model_path.parent / f"{task}__sample.csv")
    feats = schema["numeric_features"] + schema["categorical_features"]
    model = joblib.load(model_path)
    pred = model.predict_proba(sample[feats])[:, 1] if schema["kind"] == "cls" else model.predict(sample[feats])
    diff = float(np.max(np.abs(pred - sample["_pred"].to_numpy())))
    rows.append({"family": schema["family"], "task": task, "tier": schema["tier"], "model": schema["model"],
                 "rows_checked": int(len(sample)), "max_abs_diff": diff, "ok": diff < 1e-9})
out = {"checked": len(rows), "all_ok": all(r["ok"] for r in rows), "rows": rows}
(ROOT / "汇总" / "model_load_verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"checked": out["checked"], "all_ok": out["all_ok"]}, ensure_ascii=False))
sys.exit(0 if out["all_ok"] else 1)
