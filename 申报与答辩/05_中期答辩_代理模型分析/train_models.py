"""P2：电脑端性能代理模型（工况 + 算法配置 [+ 观测条件] → 实验表现）。

遵循 10-19 分析计划与 GPT 训练准入草案中的方法规则：
- 按整条轨迹分组交叉验证；同轨迹全部配置、噪声种子都在同一折。
- S1 另做“留一动作模板”泛化诊断。
- 4 类模型：训练折均值基线、带二阶交互的 Ridge、随机森林、梯度提升；固定超参数，不做自动搜索。
- 各指标单独建模，不合成加权总分。
- case_id、job_id、种子、接触时间、已有评分不作输入。
- 编码、缩放全部在训练折内（Pipeline）。

作者标记：Kiro。训练数据是接触标签纠错前的 v3 评分；配对差目标有 DeepSeek 区间旁证，绝对值目标仅作描述。
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler

from common import (
    DRIVE_CATEGORICAL, DRIVE_NUMERIC, METHOD_CATEGORICAL, METHOD_NUMERIC,
    OBS_CATEGORICAL, OBS_NUMERIC, SEED, TABLES, ensure_dirs,
)

warnings.filterwarnings("ignore", category=UserWarning)

# (任务名, 数据集, 目标列, 是否排除 hold 行, 目标说明, 标签依赖)
TASKS = [
    ("S1_geom2s_mean", "S1", "geom_2.0_mean", False, "2 s 端点预测误差均值 (m)", "标签无关"),
    ("S1_geom2s_p95", "S1", "geom_2.0_p95", False, "2 s 端点预测误差 P95 (m)", "标签无关"),
    ("S1_d_right_pct", "S1", "d_right_pct", True, "RIGHT 不足率 − hold (pp)", "配对差，有区间旁证"),
    ("S1_d_negative_fp_pct", "S1", "d_negative_fp_pct", True, "近场点误报率 − hold (pp)", "配对差，有区间旁证"),
    ("S1_right_pct", "S1", "right_pct", False, "RIGHT 不足率绝对值 (%)", "绝对值，仅描述"),
    ("S2_negative_fp_pct", "S2", "negative_fp_pct", False, "近场点误报率 (%)", "绝对值，仅描述"),
    ("S2_geom2s_p95", "S2", "geom_2.0_p95", False, "2 s 端点预测误差 P95 (m)", "标签无关"),
    ("S2_d_right_pct", "S2", "d_right_pct", True, "RIGHT 不足率 − hold (pp)", "配对差，有区间旁证"),
]


def feature_lists(stage: str):
    num = DRIVE_NUMERIC + METHOD_NUMERIC
    cat = DRIVE_CATEGORICAL + METHOD_CATEGORICAL
    if stage == "S2":
        num = num + OBS_NUMERIC
        cat = cat + OBS_CATEGORICAL
    return num, cat


def make_models(num, cat):
    def pre(scale: bool):
        return ColumnTransformer([
            ("num", StandardScaler() if scale else "passthrough", num),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
        ])

    return {
        "均值基线": Pipeline([("pre", pre(False)), ("m", DummyRegressor(strategy="mean"))]),
        "Ridge(二阶交互)": Pipeline([
            ("pre", pre(True)),
            ("poly", PolynomialFeatures(degree=2, interaction_only=True, include_bias=False)),
            ("m", Ridge(alpha=1.0)),
        ]),
        "随机森林": Pipeline([("pre", pre(False)), ("m", RandomForestRegressor(
            n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=1))]),
        "梯度提升": Pipeline([("pre", pre(False)), ("m", GradientBoostingRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=SEED))]),
    }


def splits(df: pd.DataFrame, stage: str):
    groups = df["case_id"].to_numpy()
    if stage == "S1":
        yield "按轨迹5折", list(GroupKFold(n_splits=5).split(df, groups=groups))
        yield "留一动作模板", list(LeaveOneGroupOut().split(df, groups=df["template"].to_numpy()))
    else:
        # 只有 6 条轨迹：留一轨迹
        yield "留一轨迹", list(LeaveOneGroupOut().split(df, groups=groups))


def evaluate(task, data: dict):
    name, stage, target, drop_hold, desc, label_dep = task
    df = data[stage]
    if drop_hold:
        df = df[df["method"] != "hold"]
    df = df.dropna(subset=[target]).reset_index(drop=True)
    num, cat = feature_lists(stage)
    X, y = df[num + cat], df[target].to_numpy(float)

    score_rows, oof_rows, imp_rows = [], [], []
    for scheme, folds in splits(df, stage):
        preds = {}
        for mname, model in make_models(num, cat).items():
            oof = np.full(len(df), np.nan)
            fold_mae = []
            for tr, te in folds:
                model.fit(X.iloc[tr], y[tr])
                oof[te] = model.predict(X.iloc[te])
                fold_mae.append(np.mean(np.abs(oof[te] - y[te])))
            preds[mname] = oof
            err = np.abs(oof - y)
            group_mae = pd.Series(err).groupby(df["case_id"]).mean()  # 每条轨迹等权
            ss_res = np.sum((y - oof) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            rho = spearmanr(y, oof).statistic if np.std(oof) > 0 else np.nan
            score_rows.append({
                "task": name, "target": desc, "label_dependency": label_dep, "scheme": scheme,
                "model": mname, "rows": len(df), "groups": int(df["case_id"].nunique()),
                "folds": len(folds), "MAE": float(err.mean()),
                "MAE_group_equal": float(group_mae.mean()),
                "MAE_fold_std": float(np.std(fold_mae)),
                "worst_group_MAE": float(group_mae.max()),
                "R2_oof": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
                "spearman_oof": float(rho) if rho == rho else np.nan,
            })
        base = next(r for r in score_rows if r["task"] == name and r["scheme"] == scheme and r["model"] == "均值基线")
        for r in score_rows:
            if r["task"] == name and r["scheme"] == scheme:
                r["skill_vs_baseline"] = 1 - r["MAE_group_equal"] / base["MAE_group_equal"] if base["MAE_group_equal"] > 0 else np.nan
        for mname, oof in preds.items():
            oof_rows.append(pd.DataFrame({
                "task": name, "scheme": scheme, "model": mname, "case_id": df["case_id"],
                "config_id": df["config_id"], "condition": df["condition"],
                "preprocessing": df["preprocessing"], "y_true": y, "y_pred": oof,
            }))

    # 置换重要性：主验证方案下组等权 MAE 最好的非基线模型，在每个留出折上计算
    main_scheme = "按轨迹5折" if stage == "S1" else "留一轨迹"
    cand = [r for r in score_rows if r["task"] == name and r["scheme"] == main_scheme and r["model"] != "均值基线"]
    best = min(cand, key=lambda r: r["MAE_group_equal"])
    folds = dict(splits(df, stage))[main_scheme]
    model = make_models(num, cat)[best["model"]]
    per_fold = []
    for k, (tr, te) in enumerate(folds):
        model.fit(X.iloc[tr], y[tr])
        res = permutation_importance(model, X.iloc[te], y[te], scoring="neg_mean_absolute_error",
                                     n_repeats=10, random_state=SEED + k, n_jobs=1)
        per_fold.append(res.importances_mean)
    per_fold = np.array(per_fold)
    for j, feat in enumerate(num + cat):
        imp_rows.append({
            "task": name, "model": best["model"], "feature": feat,
            "importance_mean": float(per_fold[:, j].mean()),
            "importance_fold_std": float(per_fold[:, j].std()),
            "positive_folds": int((per_fold[:, j] > 0).sum()), "folds": len(folds),
        })
    return score_rows, pd.concat(oof_rows), imp_rows, best["model"]


def main():
    ensure_dirs()
    data = {s: pd.read_csv(TABLES / f"{s.lower()}_rows.csv") for s in ("S1", "S2")}
    scores, oofs, imps, best = [], [], [], {}
    for task in TASKS:
        s, o, i, b = evaluate(task, data)
        scores += s
        oofs.append(o)
        imps += i
        best[task[0]] = b
        main_rows = [r for r in s if r["model"] == b]
        print(task[0], b, " | ".join(f"{r['scheme']}: skill={r['skill_vs_baseline']:.3f} R2={r['R2_oof']:.3f}" for r in main_rows), flush=True)
    pd.DataFrame(scores).to_csv(TABLES / "model_scores.csv", index=False, encoding="utf-8-sig")
    pd.concat(oofs).to_csv(TABLES / "oof_predictions.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(imps).to_csv(TABLES / "permutation_importance.csv", index=False, encoding="utf-8-sig")
    with open(TABLES / "best_models.json", "w", encoding="utf-8") as fh:
        json.dump({"seed": SEED, "best_model_by_task": best,
                   "selection_rule": "主验证方案下每条轨迹等权 MAE 最小的非基线模型",
                   "admission_rule": "只有在留出轨迹上 skill_vs_baseline > 0 的任务，才用于解释"},
                  fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
