"""独立进程加载已保存的模型，用原始字段样例重新预测并与训练时的预测比对。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
失败条件（任一即退出码 1）：
- 一个模型都没找到；
- 某模型族应保存的模型（tiers.csv 中 A/B 档）与实际保存的模型数量或名单不一致；
- 任一模型加载失败、缺 schema/样例，或预测与训练时不一致。
"""
import json
import sys
import traceback
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ["M1_核心预测方法", "M2a_观测扰动与预处理", "M2b_状态估计筛选", "M3_二级处理联合", "M4_趋势增益精化"]

rows, problems = [], []
for fam in FAMILIES:
    tiers_path = ROOT / fam / "results" / "tiers.csv"
    if not tiers_path.exists():
        problems.append(f"{fam}: 缺少 results/tiers.csv")
        continue
    tiers = pd.read_csv(tiers_path)
    expected = set(tiers.loc[tiers.tier.isin(["A", "B"]), "task"])
    found = {p.stem for p in (ROOT / fam / "model").glob("*.joblib")}
    if expected != found:
        problems.append(f"{fam}: 应保存 {len(expected)} 个模型，实际 {len(found)} 个；"
                        f"缺 {sorted(expected - found)}，多 {sorted(found - expected)}")
    for task in sorted(found):
        model_path = ROOT / fam / "model" / f"{task}.joblib"
        try:
            schema = json.loads((model_path.parent / f"{task}__schema.json").read_text(encoding="utf-8"))
            sample = pd.read_csv(model_path.parent / f"{task}__sample.csv")
            feats = schema["numeric_features"] + schema["categorical_features"]
            model = joblib.load(model_path)
            pred = model.predict_proba(sample[feats])[:, 1] if schema["kind"] == "cls" else model.predict(sample[feats])
            diff = float(np.max(np.abs(pred - sample["_pred"].to_numpy())))
            ok = diff < 1e-9
            rows.append({"family": schema["family"], "task": task, "tier": schema["tier"], "model": schema["model"],
                         "rows_checked": int(len(sample)), "max_abs_diff": diff, "ok": ok})
            if not ok:
                problems.append(f"{fam}/{task}: 预测不一致，最大差 {diff:g}")
        except Exception as exc:  # noqa: BLE001
            rows.append({"family": fam, "task": task, "ok": False, "error": repr(exc)})
            problems.append(f"{fam}/{task}: 加载或预测失败 {exc!r}\n{traceback.format_exc()[-400:]}")

if not rows:
    problems.append("一个模型都没有找到")
out = {"checked": len(rows), "all_ok": not problems, "problems": problems, "rows": rows}
(ROOT / "汇总" / "model_load_verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"checked": out["checked"], "all_ok": out["all_ok"], "problems": problems[:5]}, ensure_ascii=False))
sys.exit(0 if out["all_ok"] else 1)
