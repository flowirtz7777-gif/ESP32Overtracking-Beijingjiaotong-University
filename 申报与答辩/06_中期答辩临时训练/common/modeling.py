"""代理模型训练引擎。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

流程：按任务 → 按验证方案 → 按模型 → 按折 拟合并得到折外预测；
选出主方案下最优非基线模型 → 分档 → 置换重要性 → 残差与分段误差 →（可选）外部检验、学习曲线、PDP →
全量重拟合并保存 A/B 档模型。
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (GradientBoostingClassifier, GradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             precision_recall_curve, roc_auc_score, roc_curve)
from sklearn.model_selection import GridSearchCV, GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler

from .config import FEATURE_GROUPS, FEATURE_LABEL, HEADER, N_PERM_REPEATS, SAFETY_RECALL, SEED, TIER_A, target_label

warnings.filterwarnings("ignore")

TUNE_JOBS = 8  # 只有 M3 调参；其余窗口单进程，20 核机器上总并发约 12
GRIDS = {
    "随机森林": {"m__max_depth": [None, 12], "m__min_samples_leaf": [1, 3], "m__max_features": [1.0, 0.5]},
    "梯度提升": {"m__n_estimators": [200, 400], "m__max_depth": [2, 3], "m__learning_rate": [0.05, 0.1]},
}


@dataclass
class Task:
    target: str
    kind: str = "reg"            # reg | cls
    label_dep: str = "绝对值"     # 标签无关 | 配对差 | 绝对值
    exclude_hold: bool = False
    job_level: bool = False      # 几何目标：每个作业只保留一行
    key: bool = False            # 进入关键图
    note: str = ""


@dataclass
class Family:
    name: str                    # M1 ...
    title: str
    out: Path
    train: pd.DataFrame
    num: list
    cat: list
    tasks: list
    schemes: dict                # 名称 -> callable(df) -> folds
    main_scheme: str
    external: pd.DataFrame | None = None
    tune: bool = False
    learning_curve: list = field(default_factory=list)
    pdp_features: list = field(default_factory=list)
    segments: list = field(default_factory=lambda: ["condition", "template", "v_B_mps", "config_id"])
    score_note: str = ""


# ---------------- 验证方案 ----------------
def by_group_kfold(col: str, k: int):
    def f(df):
        g = df[col].to_numpy()
        k_eff = min(k, len(np.unique(g)))
        return list(GroupKFold(n_splits=k_eff).split(df, groups=g))
    return f


def leave_one(col: str):
    def f(df):
        return list(LeaveOneGroupOut().split(df, groups=df[col].to_numpy()))
    return f


# ---------------- 模型工厂 ----------------
def _pre(num, cat, scale):
    return ColumnTransformer([
        ("num", StandardScaler() if scale else "passthrough", num),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
    ])


def make_models(kind, num, cat):
    if kind == "reg":
        return {
            "基线": Pipeline([("pre", _pre(num, cat, False)), ("m", DummyRegressor())]),
            "Ridge": Pipeline([("pre", _pre(num, cat, True)),
                               ("poly", PolynomialFeatures(2, interaction_only=True, include_bias=False)),
                               ("m", Ridge(alpha=1.0))]),
            "随机森林": Pipeline([("pre", _pre(num, cat, False)), ("m", RandomForestRegressor(
                n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=1))]),
            "梯度提升": Pipeline([("pre", _pre(num, cat, False)), ("m", GradientBoostingRegressor(
                n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=SEED))]),
        }
    return {
        "基线": Pipeline([("pre", _pre(num, cat, False)), ("m", DummyClassifier(strategy="prior"))]),
        "逻辑回归": Pipeline([("pre", _pre(num, cat, True)),
                          ("poly", PolynomialFeatures(2, interaction_only=True, include_bias=False)),
                          ("m", LogisticRegression(C=1.0, max_iter=3000))]),
        "随机森林": Pipeline([("pre", _pre(num, cat, False)), ("m", RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=1))]),
        "梯度提升": Pipeline([("pre", _pre(num, cat, False)), ("m", GradientBoostingClassifier(
            n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=SEED))]),
    }


class ConstProba:
    """训练折只有一个类别时的常数分类器。"""

    def __init__(self, p):
        self.p = float(p)

    def predict_proba(self, X):
        return np.column_stack([np.full(len(X), 1 - self.p), np.full(len(X), self.p)])


def predict(model, X, kind):
    return model.predict_proba(X)[:, 1] if kind == "cls" else model.predict(X)


def fit_model(name, base, X, y, groups, kind, tune):
    if kind == "cls" and len(np.unique(y)) < 2:
        return ConstProba(y.mean()), None
    if tune and name in GRIDS:
        inner = GroupKFold(n_splits=min(3, len(np.unique(groups))))
        gs = GridSearchCV(clone(base), GRIDS[name], cv=inner, n_jobs=TUNE_JOBS, refit=True,
                          scoring="neg_mean_absolute_error" if kind == "reg" else "neg_brier_score")
        gs.fit(X, y, groups=groups)
        return gs.best_estimator_, gs.best_params_
    m = clone(base)
    m.fit(X, y)
    return m, None


def units_per_fit(name, tune):
    return 1 + (len(list(_grid_iter(GRIDS[name]))) * 3) // TUNE_JOBS if tune and name in GRIDS else 1


def _grid_iter(grid):
    from itertools import product
    keys = list(grid)
    for vals in product(*[grid[k] for k in keys]):
        yield dict(zip(keys, vals))


# ---------------- 指标 ----------------
def reg_metrics(y, p, groups):
    err = np.abs(y - p)
    ge = pd.Series(err).groupby(np.asarray(groups)).mean()
    ss_tot = np.sum((y - y.mean()) ** 2)
    rho = spearmanr(y, p).statistic if np.std(p) > 0 and np.std(y) > 0 else np.nan
    return {"MAE": float(err.mean()), "MAE_group_equal": float(ge.mean()), "worst_group_MAE": float(ge.max()),
            "R2": float(1 - np.sum((y - p) ** 2) / ss_tot) if ss_tot > 0 else np.nan,
            "spearman": float(rho) if rho == rho else np.nan}


def cls_metrics(y, p):
    two = len(np.unique(y)) == 2
    return {"AUC": float(roc_auc_score(y, p)) if two else np.nan,
            "AP": float(average_precision_score(y, p)) if two else np.nan,
            "Brier": float(brier_score_loss(y, np.clip(p, 0, 1))), "positive_rate": float(np.mean(y))}


def metric_for_perm(kind, y, p):
    return np.mean(np.abs(y - p)) if kind == "reg" else brier_score_loss(y, np.clip(p, 0, 1))


# ---------------- 主流程 ----------------
def task_frame(fam: Family, task: Task, df: pd.DataFrame | None = None):
    d = fam.train if df is None else df
    if task.exclude_hold:
        d = d[d.method != "hold"]
    if task.job_level:
        d = d.drop_duplicates("job_id")
    d = d.dropna(subset=[task.target])
    return d.reset_index(drop=True)


def estimate_units(fam: Family) -> int:
    total = 0
    for task in fam.tasks:
        df = task_frame(fam, task)
        if df.empty:
            continue
        names = list(make_models(task.kind, fam.num, fam.cat))
        for sname, sf in fam.schemes.items():
            nf = len(sf(df))
            for n in names:
                total += nf * units_per_fit(n, fam.tune and sname == fam.main_scheme)
        total += len(fam.schemes[fam.main_scheme](df))  # 置换重要性
        total += 2                                       # 全量重拟合 + 外部检验
    for t in fam.learning_curve:
        total += 21
    total += 10
    return total


def run_family(fam: Family, mon) -> dict:
    out = fam.out
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "model").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    score_rows, tier_rows, imp_rows, seg_rows = [], [], [], []
    oof_store, ext_store, cls_store, final_models, pdp_store = {}, {}, {}, {}, {}
    feats = fam.num + fam.cat

    for ti, task in enumerate(fam.tasks, 1):
        df = task_frame(fam, task)
        if df.empty or df[task.target].nunique() < 2:
            mon.line(f"[{fam.name}] 跳过 {task.target}：没有变化")
            continue
        X, y, g = df[feats], df[task.target].to_numpy(float), df["case_id"].to_numpy()
        mon.line(f"[{fam.name}] 任务 {ti}/{len(fam.tasks)} {target_label(task.target)}（{task.label_dep}），{len(df)} 行 / {len(np.unique(g))} 条轨迹")
        models = make_models(task.kind, fam.num, fam.cat)
        fold_models = {}
        per_scheme_oof = {}
        for sname, sf in fam.schemes.items():
            folds = sf(df)
            tune = fam.tune and sname == fam.main_scheme
            per_scheme_oof[sname] = {}
            for mname, base in models.items():
                oof = np.full(len(df), np.nan)
                fms, params = [], []
                for k, (tr, te) in enumerate(folds):
                    mon.set_stage(f"{task.target[:18]} {sname} {mname} 折{k+1}/{len(folds)}")
                    m, bp = fit_model(mname, base, X.iloc[tr], y[tr], g[tr], task.kind, tune)
                    oof[te] = predict(m, X.iloc[te], task.kind)
                    fms.append(m)
                    params.append(bp)
                    mon.tick(units_per_fit(mname, tune))
                per_scheme_oof[sname][mname] = oof
                if sname == fam.main_scheme:
                    fold_models[mname] = (fms, folds, params)
                met = reg_metrics(y, oof, g) if task.kind == "reg" else cls_metrics(y.astype(int), oof)
                score_rows.append({"family": fam.name, "task": task.target, "kind": task.kind, "label_dep": task.label_dep,
                                   "scheme": sname, "model": mname, "rows": len(df), "groups": int(len(np.unique(g))),
                                   "folds": len(folds), "tuned": bool(tune and mname in GRIDS),
                                   "best_params": json.dumps([p for p in params if p], ensure_ascii=False) if tune else "",
                                   **met})
            # 相对基线的 skill
            rows = [r for r in score_rows if r["family"] == fam.name and r["task"] == task.target and r["scheme"] == sname]
            base_r = next(r for r in rows if r["model"] == "基线")
            for r in rows:
                if task.kind == "reg":
                    r["skill"] = 1 - r["MAE_group_equal"] / base_r["MAE_group_equal"] if base_r["MAE_group_equal"] > 0 else np.nan
                else:
                    r["skill"] = 1 - r["Brier"] / base_r["Brier"] if base_r["Brier"] > 0 else np.nan
            best_now = min((r for r in rows if r["model"] != "基线"),
                           key=lambda r: r["MAE_group_equal"] if task.kind == "reg" else r["Brier"])
            mon.line(f"    {sname:10s} 最优 {best_now['model']:6s} skill={best_now['skill']:+.3f}"
                     + (f" R²={best_now['R2']:.3f}" if task.kind == "reg" else f" AUC={best_now['AUC']:.3f}"))

        # 选最优模型（主方案，非基线）
        main_rows = [r for r in score_rows if r["family"] == fam.name and r["task"] == task.target and r["scheme"] == fam.main_scheme]
        best = min((r for r in main_rows if r["model"] != "基线"),
                   key=lambda r: r["MAE_group_equal"] if task.kind == "reg" else r["Brier"])
        bname = best["model"]
        oof_store[task.target] = {s: pd.DataFrame({"case_id": df.case_id, "condition": df.condition, "config_id": df.config_id,
                                                   "template": df.template, "v_B_mps": df.v_B_mps,
                                                   "variant": df.get("variant", ""), "y_true": y,
                                                   "y_pred": per_scheme_oof[s][bname], "y_base": per_scheme_oof[s]["基线"]})
                                  for s in fam.schemes}

        # 置换重要性（主方案各留出折）
        fms, folds, _ = fold_models[bname]
        rng = np.random.default_rng(SEED)
        groups_to_test = {f: [f] for f in feats}
        for gname, cols in FEATURE_GROUPS.items():
            cols = [c for c in cols if c in feats]
            if len(cols) > 1:
                groups_to_test[f"[组] {gname}"] = cols
        per_fold = {k: [] for k in groups_to_test}
        for (tr, te), m in zip(folds, fms):
            Xte, yte = X.iloc[te].reset_index(drop=True), y[te]
            base_score = metric_for_perm(task.kind, yte, predict(m, Xte, task.kind))
            for gname, cols in groups_to_test.items():
                inc = []
                for _ in range(N_PERM_REPEATS):
                    Xp = Xte.copy()
                    idx = rng.permutation(len(Xp))
                    for c in cols:
                        Xp[c] = Xte[c].to_numpy()[idx]
                    inc.append(metric_for_perm(task.kind, yte, predict(m, Xp, task.kind)) - base_score)
                per_fold[gname].append(np.mean(inc))
            mon.tick(1, f"{task.target[:18]} 置换重要性")
        for gname, vals in per_fold.items():
            imp_rows.append({"family": fam.name, "task": task.target, "model": bname, "feature": gname,
                             "label": gname if gname.startswith("[组]") else FEATURE_LABEL.get(gname, gname),
                             "is_group": gname.startswith("[组]"), "importance_mean": float(np.mean(vals)),
                             "importance_fold_std": float(np.std(vals)), "positive_folds": int(np.sum(np.array(vals) > 0)),
                             "folds": len(vals)})

        # 残差与分段误差（回归，主方案折外）
        if task.kind == "reg":
            o = oof_store[task.target][fam.main_scheme]
            o = o.assign(abs_err=(o.y_true - o.y_pred).abs(), resid=o.y_true - o.y_pred)
            for seg in fam.segments + ["variant"]:
                if seg in o and o[seg].nunique() > 1:
                    s = o.groupby(seg).agg(n=("abs_err", "size"), MAE=("abs_err", "mean"), mean_resid=("resid", "mean"))
                    for k2, r in s.iterrows():
                        seg_rows.append({"family": fam.name, "task": task.target, "segment": seg, "value": str(k2), **r.to_dict()})
            worst = o.groupby(["case_id", "condition"]).abs_err.mean().sort_values(ascending=False).head(10)
            for (c, cond), v in worst.items():
                seg_rows.append({"family": fam.name, "task": task.target, "segment": "最难预测前10（轨迹×条件）",
                                 "value": f"{c} | {cond}", "n": np.nan, "MAE": v, "mean_resid": np.nan})

        # 全量重拟合（M3 主方案调参时同样用内层分组调参）
        mon.set_stage(f"{task.target[:18]} 全量重拟合 {bname}")
        final, final_params = fit_model(bname, models[bname], X, y, g, task.kind, fam.tune)
        final_models[task.target] = (final, bname, final_params)
        mon.tick(1)

        # 外部检验（只评一次，模型已在开发集上定型）
        ext_ok = None
        if fam.external is not None:
            de = task_frame(fam, task, fam.external)
            if not de.empty:
                Xe, ye, ge = de[feats], de[task.target].to_numpy(float), de["case_id"].to_numpy()
                pe = predict(final, Xe, task.kind)
                pb = np.full(len(de), y.mean())
                if task.kind == "reg":
                    me, mb = reg_metrics(ye, pe, ge), reg_metrics(ye, pb, ge)
                    me["skill"] = 1 - me["MAE_group_equal"] / mb["MAE_group_equal"] if mb["MAE_group_equal"] > 0 else np.nan
                else:
                    me, mb = cls_metrics(ye.astype(int), pe), cls_metrics(ye.astype(int), pb)
                    me["skill"] = 1 - me["Brier"] / mb["Brier"] if mb["Brier"] > 0 else np.nan
                score_rows.append({"family": fam.name, "task": task.target, "kind": task.kind, "label_dep": task.label_dep,
                                   "scheme": "外部检验(12条选择轨迹)", "model": bname, "rows": len(de),
                                   "groups": int(len(np.unique(ge))), "folds": 1, "tuned": bool(fam.tune and bname in GRIDS),
                                   "best_params": json.dumps(final_params, ensure_ascii=False) if final_params else "", **me})
                ext_store[task.target] = pd.DataFrame({"case_id": de.case_id, "condition": de.condition, "config_id": de.config_id,
                                                       "variant": de.get("variant", ""), "y_true": ye, "y_pred": pe, "y_base": pb})
                ext_ok = me["skill"]
                mon.line(f"    外部检验   {bname:6s} skill={me['skill']:+.3f}"
                         + (f" R²={me['R2']:.3f}" if task.kind == "reg" else f" AUC={me['AUC']:.3f}"))
        mon.tick(1)

        # 分类：混淆矩阵与阈值
        if task.kind == "cls":
            o = oof_store[task.target][fam.main_scheme]
            thr_safe = safety_threshold(o.y_true.to_numpy().astype(int), o.y_pred.to_numpy())
            evald = ext_store.get(task.target, o)
            src = "外部检验" if task.target in ext_store else f"{fam.main_scheme} 折外"
            yt, pp = evald.y_true.to_numpy().astype(int), evald.y_pred.to_numpy()
            cms = {}
            for tname, thr in (("默认阈值 0.5", 0.5), (f"安全优先（开发集召回≥{SAFETY_RECALL:.0%}）", thr_safe)):
                cm = confusion_matrix(yt, (pp >= thr).astype(int), labels=[0, 1])
                cms[tname] = {"threshold": float(thr), "matrix": cm.tolist(),
                              "recall": float(cm[1, 1] / max(1, cm[1].sum())), "precision": float(cm[1, 1] / max(1, cm[:, 1].sum()))}
            cls_store[task.target] = {"source": src, "confusion": cms, "y": yt, "p": pp}

        # 分档
        tier_rows.append(tier_for(fam, task, score_rows, bname, ext_ok))
        t = tier_rows[-1]
        mon.line(f"    ⇒ 最优 {bname}，分档 {t['tier']}（{t['reason']}）")

        # PDP
        if fam.pdp_features and task.key and not isinstance(final, ConstProba):
            try:
                pdp_store[task.target] = pdp(final, X, fam.pdp_features, task.kind)
            except Exception as exc:  # noqa: BLE001
                mon.line(f"    PDP 失败（不影响训练结果）：{exc!r}")

    # 学习曲线
    lc_rows = []
    if fam.learning_curve and fam.external is not None:
        lc_rows = learning_curve(fam, mon, final_models)

    # 保存结果
    res = out / "results"
    scores = pd.DataFrame(score_rows)
    scores.to_csv(res / "scores.csv", index=False, encoding="utf-8-sig")
    tiers = pd.DataFrame(tier_rows)
    tiers.to_csv(res / "tiers.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(imp_rows).to_csv(res / "permutation_importance.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(seg_rows).to_csv(res / "segment_errors.csv", index=False, encoding="utf-8-sig")
    pd.concat([d.assign(task=t, scheme=s) for t, ss in oof_store.items() for s, d in ss.items()]).to_csv(
        res / "oof_best_and_baseline.csv.gz", index=False, encoding="utf-8-sig", compression="gzip")
    if ext_store:
        pd.concat([d.assign(task=t) for t, d in ext_store.items()]).to_csv(res / "external_predictions.csv", index=False, encoding="utf-8-sig")
    if cls_store:
        with open(res / "confusion_matrices.json", "w", encoding="utf-8") as fh:
            json.dump({t: {"source": v["source"], **v["confusion"]} for t, v in cls_store.items()}, fh, ensure_ascii=False, indent=2)
    if lc_rows:
        pd.DataFrame(lc_rows).to_csv(res / "learning_curve.csv", index=False, encoding="utf-8-sig")
    if pdp_store:
        with open(res / "pdp.json", "w", encoding="utf-8") as fh:
            json.dump(pdp_store, fh, ensure_ascii=False, indent=2)

    # 保存 A/B 档模型 + 原始字段样例（用于独立进程加载验证）
    saved = []
    for _, t in tiers.iterrows():
        if t.tier not in ("A", "B"):
            continue
        final, bname, params = final_models[t.task]
        if isinstance(final, ConstProba):
            continue
        path = out / "model" / f"{t.task}.joblib"
        joblib.dump(final, path)
        sample = task_frame(fam, next(x for x in fam.tasks if x.target == t.task)).head(50)
        sample_pred = predict(final, sample[feats], t.kind)
        sample[feats].assign(_pred=sample_pred).to_csv(out / "model" / f"{t.task}__sample.csv", index=False, encoding="utf-8-sig")
        schema = {"header": HEADER, "family": fam.name, "task": t.task, "target_label": target_label(t.task), "kind": t.kind,
                  "model": bname, "tier": t.tier, "params": params, "numeric_features": fam.num, "categorical_features": fam.cat,
                  "categories": {c: sorted(map(str, fam.train[c].unique())) for c in fam.cat},
                  "numeric_ranges": {c: [float(fam.train[c].min()), float(fam.train[c].max())] for c in fam.num},
                  "training_rows": int(len(task_frame(fam, next(x for x in fam.tasks if x.target == t.task)))),
                  "output": "正类概率" if t.kind == "cls" else target_label(t.task)}
        with open(out / "model" / f"{t.task}__schema.json", "w", encoding="utf-8") as fh:
            json.dump(schema, fh, ensure_ascii=False, indent=2)
        saved.append(t.task)

    mon.set_stage("出图")
    from .figures import family_figures
    family_figures(fam, scores, tiers, pd.DataFrame(imp_rows), oof_store, ext_store, cls_store, lc_rows, pdp_store,
                   pd.DataFrame(seg_rows))
    mon.tick(5)

    mon.line("")
    mon.line(f"[{fam.name}] 准入总表")
    for _, t in tiers.iterrows():
        mon.line(f"  {t.tier}  {target_label(t.task):28s} {t.model:6s} 主方案 skill={t.main_skill:+.3f} "
                 + (f"R²={t.main_R2:.3f}" if t.kind == "reg" else f"AUC={t.main_AUC:.3f}")
                 + (f" 外部 skill={t.external_skill:+.3f}" if t.external_skill == t.external_skill else ""))
    return {"tiers": tiers[["task", "tier"]].to_dict("records"), "saved_models": saved}


def tier_for(fam, task, score_rows, bname, ext_skill):
    rows = [r for r in score_rows if r["family"] == fam.name and r["task"] == task.target and r["model"] == bname]
    main = next(r for r in rows if r["scheme"] == fam.main_scheme)
    skills = {r["scheme"]: r["skill"] for r in rows}
    all_pos = all(v == v and v > 0 for v in skills.values())
    if task.kind == "reg":
        strong = main["skill"] >= TIER_A["skill"] and main["R2"] >= TIER_A["r2"]
    else:
        strong = main["AUC"] == main["AUC"] and main["AUC"] >= TIER_A["auc"] and main["skill"] > 0
    if strong and all_pos:
        tier, reason = "A", "达到 A 档阈值，且所有验证方案都优于基线"
    elif main["skill"] > 0:
        bad = [s for s, v in skills.items() if not (v == v and v > 0)]
        tier = "B"
        reason = ("主方案未达 A 档阈值" if not strong else "") + ("；" if not strong and bad else "") + \
                 (f"{'、'.join(bad)} 未优于基线" if bad else "")
    else:
        tier, reason = "C", "主方案不优于基线"
    return {"family": fam.name, "task": task.target, "target_label": target_label(task.target), "kind": task.kind,
            "label_dep": task.label_dep, "model": bname, "tier": tier, "reason": reason,
            "main_skill": main["skill"], "main_R2": main.get("R2", np.nan), "main_AUC": main.get("AUC", np.nan),
            "external_skill": ext_skill if ext_skill is not None else np.nan,
            **{f"skill[{s}]": v for s, v in skills.items()}}


def safety_threshold(y, p):
    if y.sum() == 0:
        return 0.5
    thr = np.unique(p)[::-1]
    for t in thr:
        if ((p >= t) & (y == 1)).sum() / y.sum() >= SAFETY_RECALL:
            return float(t)
    return float(thr[-1])


def pdp(model, X, features, kind):
    from sklearn.inspection import partial_dependence
    res = {}
    Xs = X.sample(min(1500, len(X)), random_state=SEED)
    rm = "predict_proba" if kind == "cls" else "auto"
    for f in features:
        if f in X and X[f].nunique() > 1:
            r = partial_dependence(model, Xs, [f], kind="average", response_method=rm, grid_resolution=10)
            res[f] = {"grid": [float(v) for v in r["grid_values"][0]], "avg": [float(v) for v in r["average"][0]]}
    if all(f in X for f in ("margin_m", "confirmation_s")):
        r = partial_dependence(model, Xs, ["margin_m", "confirmation_s"], kind="average", response_method=rm, grid_resolution=10)
        res["margin_m×confirmation_s"] = {"grid": [[float(v) for v in gv] for gv in r["grid_values"]],
                                          "avg": np.asarray(r["average"][0]).tolist()}
    return res


def learning_curve(fam, mon, final_models):
    rows = []
    rng = np.random.default_rng(SEED)
    feats = fam.num + fam.cat
    cases = np.array(sorted(fam.train.case_id.unique()))
    for tname in fam.learning_curve:
        task = next(t for t in fam.tasks if t.target == tname)
        if tname not in final_models:
            continue
        _, bname, _ = final_models[tname]
        base = make_models(task.kind, fam.num, fam.cat)[bname]
        df, de = task_frame(fam, task), task_frame(fam, task, fam.external)
        Xe, ye, ge = de[feats], de[tname].to_numpy(float), de.case_id.to_numpy()
        for n in (5, 10, 15, 20, len(cases)):
            reps = 1 if n >= len(cases) else 5
            for r in range(reps):
                pick = cases if n >= len(cases) else rng.choice(cases, n, replace=False)
                sub = df[df.case_id.isin(pick)]
                mon.set_stage(f"学习曲线 {tname[:14]} n={n} r={r+1}")
                m, _ = fit_model(bname, base, sub[feats], sub[tname].to_numpy(float), sub.case_id.to_numpy(), task.kind, False)
                pe = predict(m, Xe, task.kind)
                pb = np.full(len(de), sub[tname].mean())
                if task.kind == "reg":
                    a, b = reg_metrics(ye, pe, ge), reg_metrics(ye, pb, ge)
                    rows.append({"task": tname, "model": bname, "n_traj": n, "rep": r, "MAE_group_equal": a["MAE_group_equal"],
                                 "baseline_MAE_group_equal": b["MAE_group_equal"], "R2": a["R2"],
                                 "skill": 1 - a["MAE_group_equal"] / b["MAE_group_equal"]})
                else:
                    a, b = cls_metrics(ye.astype(int), pe), cls_metrics(ye.astype(int), pb)
                    rows.append({"task": tname, "model": bname, "n_traj": n, "rep": r, "AUC": a["AUC"], "Brier": a["Brier"],
                                 "baseline_Brier": b["Brier"], "skill": 1 - a["Brier"] / b["Brier"]})
                mon.tick(1)
        mon.line(f"    学习曲线 {target_label(tname)} 完成")
    return rows
