"""P0 数据整理与探索分析。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

读 Z 盘已有评分（只读），整理成统一字段的分析表，补端点误差、配对差和分类目标，
记录 SHA256 与行数守恒，并输出探索图（目标分布、输入/输出相关矩阵、轨迹相似度、特征与目标关系）。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common.config import (  # noqa: E402
    AFT, DATA, DATASETS, FEATURE_LABEL, HEADER, JOB_DIRS, SOURCES, target_label,
)
from common.monitor import run_main  # noqa: E402

FIG = ROOT / "P0_数据整理" / "figures"
PAIRED = ["right_pct", "right_miss_rate", "right_lead_p10_s", "negative_fp_pct", "frame_fpr_pct",
          "common_2s_fpr_pct", "geom_2.0_mean", "geom_2.0_p95"]
GEOM = [f"geom_{h}_{s}" for h in ("0.3", "1.0", "2.0") for s in ("mean", "p95", "max")]
KEEP_SCORES = ["right_pct", "stratified_right_pct", "right_contacts", "right_late", "right_miss", "right_no_before",
               "right_lead_p10_s", "right_lead_median_s", "negative_count", "negative_fp", "negative_fp_pct",
               "frame_fpr_pct", "frame_recall_pct", "common_2s_reference_fpr_pct"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_profiles: dict = {}
_read_files: dict = {}  # 实际读取的每个源文件 -> sha256，用于可复现绑定


def _record(path: Path):
    key = str(path)
    if key not in _read_files:
        _read_files[key] = sha256(path)


def profile(partition: str, case: str) -> dict:
    key = (partition, case)
    if key not in _profiles:
        p = DATASETS / partition / case / "profile.json"
        _record(p)
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)["design"]
        entry, ret = float(d["entry_rate_abs_deg_s"]), float(d["return_rate_abs_deg_s"])
        # 选择集 profile 没有 template / base_rate 字段：按入弯与回正速率的关系推出（与开发集定义一致）
        template = d.get("template") or ("symmetric" if entry == ret else "fast_entry" if entry > ret else "fast_return")
        _profiles[key] = {
            "v_B_mps": float(d["v_B_mps"]), "base_rate_deg_s": float(d.get("base_rate_deg_s", min(entry, ret))),
            "entry_rate_deg_s": entry, "return_rate_deg_s": ret,
            "template": template, "alpha_peak_deg": float(d["alpha_peak_abs_deg"]),
        }
    return _profiles[key]


_geom: dict = {}


def find_job(job_id: str) -> Path | None:
    for base in JOB_DIRS:
        p = base / job_id
        if p.exists():
            return p
    return None


def geometry(job_id: str) -> dict:
    if job_id not in _geom:
        out = {c: np.nan for c in GEOM}
        p = find_job(job_id)
        if p is not None:
            _record(p / "summary.json")
            with open(p / "summary.json", encoding="utf-8") as fh:
                s = json.load(fh)
            s = s[0] if isinstance(s, list) else s
            g = s.get("geometry", {})
            for h in ("0.3", "1.0", "2.0"):
                out[f"geom_{h}_mean"] = g.get(h, {}).get("mean_endpoint_error_m", np.nan)
                out[f"geom_{h}_p95"] = g.get(h, {}).get("p95_endpoint_error_m", np.nan)
                out[f"geom_{h}_max"] = g.get(h, {}).get("max_endpoint_error_m", np.nan)
        _geom[job_id] = out
    return _geom[job_id]


def parse_condition(cond: str) -> dict:
    if cond == "clean":
        return {"noise_level": 0.0, "delay_ms": 0.0, "seed": 0, "obs_family": "clean"}
    m = re.fullmatch(r"noise(\d{3})_s(\d)", cond)
    if m:
        return {"noise_level": int(m[1]) / 100, "delay_ms": 0.0, "seed": int(m[2]), "obs_family": "noise"}
    m = re.fullmatch(r"delay(\d+)", cond)
    if m:
        return {"noise_level": 0.0, "delay_ms": float(m[1]), "seed": 0, "obs_family": "delay"}
    m = re.fullmatch(r"combined(\d{3})_s(\d)", cond)
    if m:
        return {"noise_level": int(m[1]) / 100, "delay_ms": 100.0, "seed": int(m[2]), "obs_family": "combined"}
    raise ValueError(cond)


def standardize(raw: pd.DataFrame, dataset: str, score_version: str) -> pd.DataFrame:
    rows = []
    for r in raw.to_dict("records"):
        method = r["method"]
        proc = r.get("processor", r.get("preprocessing", "raw"))
        if not isinstance(proc, str):
            proc = r.get("preprocessing", "raw")
        rec = {
            "dataset": dataset, "score_version": score_version, "stage": r["stage"], "job_id": r["job_id"],
            "partition": r["partition"], "case_id": r["case_id"], "config_id": r["config_id"],
            "condition": r["condition"], "method": method, "processor": proc,
            "gain_eff": float(r["gain"]) if method != "hold" else 0.0,
            "decay_eff_s": float(r["decay_s"]) if method == "damped_linear" else 0.0,
            "accel_eff_s": float(r["acceleration_duration_s"]) if method == "bounded_second_order" else 0.0,
            "EXIT_W_s": float(r["EXIT_W_s"]), "margin_m": float(r["margin_m"]), "confirmation_s": float(r["confirmation_s"]),
        }
        rec.update(profile(r["partition"], r["case_id"]))
        rec.update(parse_condition(r["condition"]))
        rec.update({c: r[c] for c in KEEP_SCORES})
        rec.update(geometry(r["job_id"]))
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["variant"] = df.apply(lambda x: f"W{x.EXIT_W_s:g}_m{x.margin_m:g}_c{x.confirmation_s:g}", axis=1)
    df["is_base_variant"] = (df.EXIT_W_s == 2) & (df.margin_m == 0) & (df.confirmation_s == 0)
    df["common_2s_fpr_pct"] = df["common_2s_reference_fpr_pct"]
    df["right_miss_rate"] = 100 * df["right_miss"] / df["right_contacts"]
    df["any_window_miss"] = (df["right_miss"] > 0).astype(int)
    df["any_no_before"] = (df["right_no_before"] > 0).astype(int)
    df["fp_budget_pass"] = ((df.negative_fp_pct <= 5) & (df.frame_fpr_pct <= 0.5) & (df.common_2s_fpr_pct <= 0.5)).astype(int)
    return df


def add_paired(df: pd.DataFrame, prefix: str, ref_mask: pd.Series, key: list[str], exclude_ref: bool = True):
    ref = df[ref_mask].set_index(key)[PAIRED]
    if ref.index.duplicated().any():
        raise RuntimeError(f"{prefix} 参照在 {key} 上不唯一")
    joined = df.join(ref, on=key, rsuffix="__ref")
    for t in PAIRED:
        df[f"{prefix}{t}"] = joined[t] - joined[f"{t}__ref"]
        if exclude_ref:
            df.loc[ref_mask, f"{prefix}{t}"] = np.nan
    return int(joined[f"{PAIRED[0]}__ref"].notna().sum())


def hold_rows_from_jobs(stage: str) -> pd.DataFrame:
    recs = []
    for d in sorted((AFT / "jobs").glob(f"{stage}__*")):
        _record(d / "summary.json")
        with open(d / "summary.json", encoding="utf-8") as fh:
            s = json.load(fh)
        for r in (s if isinstance(s, list) else [s]):
            r = {k: v for k, v in r.items() if k not in ("geometry", "stratum_right_rows")}
            recs.append(r)
    return pd.DataFrame(recs)


def build(mon) -> dict:
    import shutil
    for d in (DATA, FIG):  # 清空旧输出，避免混入上一次的数据表和图
        if d.exists():
            shutil.rmtree(d)
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = {"header": HEADER, "sources": {}, "outputs": {}, "notes": []}
    raw = {}
    for k, p in SOURCES.items():
        raw[k] = pd.read_csv(p, low_memory=False)
        manifest["sources"][k] = {"path": str(p), "sha256": sha256(p), "rows": int(len(raw[k]))}
        mon.tick(1, f"读入 {k}")
    hold3 = hold_rows_from_jobs("S3_hold_scoring_repair")
    manifest["sources"]["D3h_S3hold"] = {"path": str(AFT / "jobs" / "S3_hold_scoring_repair__*/summary.json"),
                                         "rows": int(len(hold3)), "jobs": int(hold3.job_id.nunique())}
    mon.tick(1, "读入 S3 保持基线作业")

    mon.set_stage("整理 D1 S1")
    d1 = standardize(raw["D1_S1"], "D1", "v3"); mon.tick(1)
    n = add_paired(d1, "d_hold_", d1.method == "hold", ["case_id"])
    manifest["outputs"]["D1"] = {"paired_hold_rows": n}

    mon.set_stage("整理 D2 S2")
    d2 = standardize(raw["D2_S2"], "D2", "v3"); mon.tick(1)
    n = add_paired(d2, "d_hold_", d2.method == "hold", ["case_id", "condition", "processor"])
    manifest["outputs"]["D2"] = {"paired_hold_rows": n}

    mon.set_stage("整理 D3 S3 修正评分 + 保持基线")
    d3 = pd.concat([standardize(raw["D3_S3"], "D3", "repaired"), standardize(hold3, "D3h", "repaired")], ignore_index=True)
    mon.tick(1)
    hold_mask = d3.method == "hold"
    n1 = add_paired(d3, "d_hold_", hold_mask, ["case_id", "condition"])
    post_ref = d3.is_base_variant & ~hold_mask
    n2 = add_paired(d3, "d_post_", post_ref, ["case_id", "config_id", "condition"])
    d3.loc[hold_mask, [c for c in d3.columns if c.startswith("d_post_")]] = np.nan
    manifest["outputs"]["D3"] = {"paired_hold_rows": n1, "paired_post_rows": n2}

    mon.set_stage("整理 D4 S4 状态估计")
    d4 = standardize(raw["D4_S4proc"], "D4", "repaired"); mon.tick(1)
    n1 = add_paired(d4, "d_hold_", d4.method == "hold", ["case_id", "condition", "processor"])
    n2 = add_paired(d4, "d_raw_", d4.processor == "raw", ["case_id", "config_id", "condition"])
    manifest["outputs"]["D4"] = {"paired_hold_rows": n1, "paired_raw_rows": n2}

    mon.set_stage("整理 D5 S4 联合精化")
    d5 = standardize(raw["D5_S4joint"], "D5", "repaired"); mon.tick(1)
    n1 = add_paired(d5, "d_hold_", d5.method == "hold", ["case_id", "condition", "variant"])
    n2 = add_paired(d5, "d_post_", d5.is_base_variant, ["case_id", "config_id", "condition"])
    key = ["case_id", "config_id", "condition", "variant"]
    overlap = d5.merge(d3[d3.partition == "selection_v2"][key], on=key, how="inner")
    manifest["outputs"]["D5"] = {"paired_hold_rows": n1, "paired_post_rows": n2, "rows_identical_to_D3_selection": int(len(overlap))}
    manifest["notes"].append("D5 中与 D3 选择集重复的行只在 M4 内使用；M3 外部检验用 D3 选择集，两者不在同一模型中合并，因此无需删除。")
    manifest["notes"].append("同一作业的 12 个后处理变体共用一次预测，端点误差相同；几何目标建模时按作业去重。")

    for name, df in (("D1", d1), ("D2", d2), ("D3", d3), ("D4", d4), ("D5", d5)):
        df.to_csv(DATA / f"{name}.csv", index=False, encoding="utf-8-sig")
        info = manifest["outputs"][name]
        info.update({
            "rows": int(len(df)), "trajectories": int(df.case_id.nunique()), "jobs": int(df.job_id.nunique()),
            "partitions": df.partition.value_counts().to_dict(), "score_version": df.score_version.unique().tolist(),
            "geometry_missing_rows": int(df["geom_2.0_mean"].isna().sum()),
            "alpha_peak_deg": sorted(df.alpha_peak_deg.unique().tolist()),
            "any_window_miss_share": round(float(df.any_window_miss.mean()), 4),
            "fp_budget_pass_share": round(float(df.fp_budget_pass.mean()), 4),
        })
        mon.tick(1, f"写出 {name}")
    # 行数守恒
    cons = {
        "D1": (manifest["sources"]["D1_S1"]["rows"], len(d1)),
        "D2": (manifest["sources"]["D2_S2"]["rows"], len(d2)),
        "D3": (manifest["sources"]["D3_S3"]["rows"] + manifest["sources"]["D3h_S3hold"]["rows"], len(d3)),
        "D4": (manifest["sources"]["D4_S4proc"]["rows"], len(d4)),
        "D5": (manifest["sources"]["D5_S4joint"]["rows"], len(d5)),
    }
    manifest["row_conservation"] = {k: {"read": int(a), "written": int(b), "ok": a == b} for k, (a, b) in cons.items()}
    if not all(v["ok"] for v in manifest["row_conservation"].values()):
        raise RuntimeError(f"行数不守恒：{manifest['row_conservation']}")
    # 可复现绑定：所有实际读取的源文件（评分 CSV、保持基线与几何误差 summary、工况 profile）逐文件 SHA256
    from common.provenance import aggregate, run_record
    for k in manifest["sources"]:
        if "sha256" in manifest["sources"][k]:
            _read_files[manifest["sources"][k]["path"]] = manifest["sources"][k]["sha256"]
    pd.DataFrame(sorted(_read_files.items()), columns=["path", "sha256"]).to_csv(
        DATA / "source_files_sha256.csv", index=False, encoding="utf-8-sig")
    kinds = {"summary.json": 0, "profile.json": 0, ".csv": 0}
    for pth in _read_files:
        for k in kinds:
            if pth.endswith(k):
                kinds[k] += 1
    manifest["source_files"] = {"count": len(_read_files), "by_kind": kinds, "aggregate_sha256": aggregate(_read_files),
                                "list": "source_files_sha256.csv"}
    manifest["run"] = run_record()
    for name in ("D1", "D2", "D3", "D4", "D5"):
        manifest["outputs"][name]["sha256"] = sha256(DATA / f"{name}.csv")
    with open(DATA / "data_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    mon.line("行数守恒：" + "；".join(f"{k} 读入 {v['read']} → 写出 {v['written']}" for k, v in manifest["row_conservation"].items()))
    mon.line(f"源文件绑定：{manifest['source_files']['count']} 个文件 {manifest['source_files']['by_kind']}，"
             f"整组指纹 {manifest['source_files']['aggregate_sha256'][:16]}…")
    for k, v in manifest["outputs"].items():
        mon.line(f"  {k}: {v['rows']} 行 / {v['trajectories']} 条轨迹 / {v['jobs']} 个作业，口径 {v['score_version']}，"
                 f"窗口漏报行占比 {v['any_window_miss_share']:.3f}，几何缺失 {v['geometry_missing_rows']}")
    explore(mon, {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5})
    return {"row_conservation": manifest["row_conservation"]}


# ---------------- 探索图（nature-figure skill 规范） ----------------
def explore(mon, data: dict):
    from common.plotting import (DIV_CMAP, PALETTE, SEQ_CMAP, apply_style, footnote, is_dark, panel_label, plt, save)

    apply_style()
    FIG.mkdir(parents=True, exist_ok=True)
    foot = HEADER
    letters = "abcdefgh"

    # 1 目标分布
    targets = ["right_pct", "right_miss_rate", "right_lead_p10_s", "negative_fp_pct", "frame_fpr_pct",
               "common_2s_fpr_pct", "geom_2.0_mean", "geom_2.0_p95"]
    for name in ("D1", "D2", "D3", "D4", "D5"):
        df = data[name]
        fig, axes = plt.subplots(2, 4, figsize=(7.2, 3.6))
        fig.subplots_adjust(wspace=0.45, hspace=0.75)
        for k, (ax, t) in enumerate(zip(axes.flat, targets)):
            v = df.drop_duplicates("job_id")[t] if t.startswith("geom") else df[t]
            ax.hist(v.dropna(), bins=40, color=PALETTE["blue_main"])
            ax.set_title(target_label(t), fontsize=6.8)
            ax.tick_params(labelsize=6)
            panel_label(ax, letters[k], x=-0.28, y=1.03)
        fig.suptitle(f"{name} 目标分布（{len(df):,} 行，{df.case_id.nunique()} 条轨迹）", fontsize=8.5, y=1.02)
        footnote(fig, foot + " 纵轴为行数；端点误差（g、h）按作业去重，因为同一作业的 12 个后处理变体共用一次预测。", y=-0.02)
        save(fig, FIG / f"01_目标分布_{name}.png")
        mon.tick(1, f"探索图 目标分布 {name}")

    # 2 输入相关矩阵 / 3 输出相关矩阵
    inputs = ["v_B_mps", "entry_rate_deg_s", "return_rate_deg_s", "gain_eff", "decay_eff_s", "accel_eff_s",
              "noise_level", "delay_ms", "EXIT_W_s", "margin_m", "confirmation_s"]
    cmap = plt.get_cmap(DIV_CMAP)

    def heat(ax, corr, labels, fs):
        im = ax.imshow(corr.to_numpy(), cmap=cmap, vmin=-1, vmax=1)
        ax.set_xticks(range(len(labels)), labels, rotation=55, ha="right", fontsize=fs)
        ax.set_yticks(range(len(labels)), labels, fontsize=fs)
        for i in range(len(labels)):
            for j in range(len(labels)):
                val = corr.iat[i, j]
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=fs - 1,
                        color="white" if is_dark(cmap((val + 1) / 2)) else "black")
        for sp in ax.spines.values():
            sp.set_visible(False)
        return im

    for name in ("D1", "D2", "D3", "D4", "D5"):
        df = data[name]
        cols = [c for c in inputs if df[c].nunique() > 1]
        X = df[cols].copy()
        for m in sorted(df.method.unique()):
            if df.method.nunique() > 1:
                X[f"method={m}"] = (df.method == m).astype(int)
        for p in sorted(df.processor.unique()):
            if df.processor.nunique() > 1:
                X[f"proc={p}"] = (df.processor == p).astype(int)
        corr = X.corr(method="spearman")
        labels = [FEATURE_LABEL.get(c, c) for c in corr.columns]
        n = len(labels)
        fig, ax = plt.subplots(figsize=(0.36 * n + 1.8, 0.32 * n + 1.2))
        im = heat(ax, corr, labels, 6.5)
        fig.colorbar(im, ax=ax, shrink=0.8, label="Spearman 相关")
        ax.set_title(f"{name} 输入相关矩阵：实验设计下各因素能否分开估计", fontsize=8)
        footnote(fig, foot + " 方法专属参数（增益、衰减时间、二阶生效时长）不适用时记为 0，因此与方法类别天然相关。", y=-0.04)
        save(fig, FIG / f"02_输入相关矩阵_{name}.png")

        outs = [t for t in targets if df[t].nunique() > 1]
        corr = df[outs].corr(method="spearman")
        labels = [target_label(c) for c in outs]
        fig, ax = plt.subplots(figsize=(4.6, 3.8))
        im = heat(ax, corr, labels, 6.5)
        fig.colorbar(im, ax=ax, shrink=0.8, label="Spearman 相关")
        ax.set_title(f"{name} 输出相关矩阵：哪些指标同涨同落、哪些此消彼长", fontsize=8)
        footnote(fig, foot, y=-0.06)
        save(fig, FIG / f"03_输出相关矩阵_{name}.png")
        mon.tick(1, f"探索图 相关矩阵 {name}")

    # 4 轨迹相似度（D3 全部 39 条轨迹）
    from scipy.cluster.hierarchy import leaves_list, linkage

    df = data["D3"][data["D3"].method != "hold"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.9))
    fig.subplots_adjust(wspace=0.55)
    for k, (ax, t) in enumerate(zip(axes, ("right_pct", "negative_fp_pct"))):
        piv = df.pivot_table(index="case_id", columns=["config_id", "condition", "variant"], values=t)
        corr = piv.T.corr(method="spearman")
        order = leaves_list(linkage(corr.to_numpy(), method="average"))
        corr = corr.iloc[order, order]
        im = ax.imshow(corr.to_numpy(), cmap=SEQ_CMAP, vmin=corr.to_numpy().min(), vmax=1)
        ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=3.8)
        ax.set_yticks(range(len(corr)), corr.index, fontsize=3.8)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(f"按{target_label(t)}的轨迹相似度（聚类排序）", fontsize=7.5)
        fig.colorbar(im, ax=ax, shrink=0.7, label="Spearman 相关")
        panel_label(ax, letters[k], x=-0.32, y=1.02)
    footnote(fig, foot + " 每条轨迹用 2 方法 × 8 条件 × 12 变体共 192 个指标值组成的向量表示；sel_ 开头为选择集。", y=-0.01)
    save(fig, FIG / "04_轨迹相似度_D3.png")
    mon.tick(1, "探索图 轨迹相似度")

    # 5 特征与目标关系（D3 开发集）
    df = data["D3"][(data["D3"].partition == "development_v2_n70000") & (data["D3"].method != "hold")]
    feats = ["v_B_mps", "entry_rate_deg_s", "noise_level", "delay_ms", "EXIT_W_s", "margin_m", "confirmation_s", "method"]
    short = {"damped_linear": "衰减", "linear": "线性"}
    fig, axes = plt.subplots(2, len(feats), figsize=(7.2, 3.6), sharey="row")
    fig.subplots_adjust(wspace=0.15, hspace=0.35)
    box_kw = dict(showfliers=False, widths=0.6, patch_artist=True,
                  boxprops=dict(facecolor=PALETTE["blue_secondary"], edgecolor=PALETTE["neutral_dark"], lw=0.6, alpha=0.55),
                  medianprops=dict(color=PALETTE["neutral_black"], lw=0.9),
                  whiskerprops=dict(lw=0.6), capprops=dict(lw=0.6))
    for j, f in enumerate(feats):
        for i, t in enumerate(("right_pct", "negative_fp_pct")):
            groups = sorted(df[f].unique(), key=str)
            axes[i, j].boxplot([df.loc[df[f] == g, t] for g in groups], **box_kw)
            axes[i, j].set_xticks(range(1, len(groups) + 1),
                                  [f"{g:g}" if isinstance(g, float) else short.get(str(g), str(g)[:4]) for g in groups], fontsize=5.5)
            axes[i, j].tick_params(axis="y", labelsize=6)
            if i == 1:
                axes[i, j].set_xlabel(FEATURE_LABEL.get(f, f), fontsize=6)
    axes[0, 0].set_ylabel(target_label("right_pct"), fontsize=6.5)
    axes[1, 0].set_ylabel(target_label("negative_fp_pct"), fontsize=6.5)
    panel_label(axes[0, 0], "a", x=-0.7, y=1.02)
    panel_label(axes[1, 0], "b", x=-0.7, y=1.02)
    fig.suptitle("D3 开发集：各输入取值下的 RIGHT 不足率（a）与近场点误报率（b）", fontsize=8.5, y=0.99)
    footnote(fig, foot + " 箱体为四分位范围，中线为中位数，须线为 1.5 倍四分位距；每格包含该取值下的全部评分行（不是独立车辆试验）。", y=-0.01)
    save(fig, FIG / "05_特征与目标关系_D3.png")
    mon.tick(1, "探索图 特征与目标关系")


class _Quiet:
    """不显示进度的空监视器（供 explore_from_saved 使用）。"""

    def tick(self, *a, **k):
        pass

    def set_stage(self, *a, **k):
        pass

    def line(self, *a, **k):
        pass


def explore_from_saved():
    """不重建数据：直接读取 data/ 中已保存的 D1–D5，重画全部 17 张探索图。返回图片路径列表。"""
    import shutil

    if FIG.exists():
        shutil.rmtree(FIG)
    data = {n: pd.read_csv(DATA / f"{n}.csv", low_memory=False) for n in ("D1", "D2", "D3", "D4", "D5")}
    explore(_Quiet(), data)
    return sorted(FIG.glob("*.png"))


if __name__ == "__main__":
    if "--figures-only" in sys.argv:
        print(f"重画 {len(explore_from_saved())} 张探索图")
        sys.exit(0)
    sys.exit(run_main("P0", 7 + 1 + 5 + 5 + 5 + 5 + 1 + 1, build))
