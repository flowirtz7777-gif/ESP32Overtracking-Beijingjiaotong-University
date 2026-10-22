# 中期答辩：首批正向评分结果（DeepSeek 执行）

**作者标记：DeepSeek 生成。** 本文件为中期答辩准备材料，非 Codex 产出。

- 执行时间：2026-10-22（北京时间）
- 数据来源：`Z:\大创内轮差项目_实验结果\科研实验_2026-10-14`
- 分支：`deepseek/midterm-defense-20261022`

---

## 状态声明（必须随图一起展示）

| 项目 | 状态 |
|---|---|
| 正向评分（numpy 路径） | **已完成** |
| 独立核验（independent close） | **按人类指令延后** |
| 可用于排名 / 训练 | **否** |
| 修正标签认证 | 0 |
| 修正评分认证 | 0 |

本文所有数值均为 **forward-only**，可作为"方法相对优劣的初步证据"，但**不构成最终验收结论**。

---

## 实验配置

| 项目 | 值 |
|---|---|
| 工况 | `v2_r2_symmetric`（v_B = 2 m/s，转角速率 2 °/s，对称模板）|
| 目标点 | 70,000（P1 重建的完整总体，6 字段 SHA 已核）|
| 帧数 | 1,854（dt = 0.02 s）|
| 评分窗口 | 2.00 – 34.06 s |
| 预测变体 | 12 组（EXIT_W ∈ {2,3} × margin ∈ {0,0.02,0.05} × confirmation ∈ {0,0.1}）|
| 对比方法 A | `damped_linear` (g=1.0, τ=1.0 s) |
| 对比方法 B | `hold`（基线）|
| 指标 | RIGHT 不足率 = (miss ∪ late) / eligible_RIGHT |

### 观测条件（8 个）

`clean`、`delay100`、`noise100_s1/s2/s3`、`combined100_s1/s2/s3`

---

## 已完成结果：clean 条件

| 方法 | RIGHT 不足率（区间）|
|---|---|
| A: `damped_linear_g1000_d1000` | **0.004% — 0.878%** |
| B: `hold` | **0.237% — 1.111%** |
| 配对差 A − B | **−0.236% — −0.233%** |

**判读**：
- 配对差区间两端均为负，**A 严格优于 B**（在本次正向评分口径下）。
- 区间宽度仅 **0.003 个百分点**（−0.236 到 −0.233），说明该配对结论对标签不确定性不敏感。
- 但 B 自身区间（0.237–1.111%）较宽，约 0.87pp，反映 `hold` 方法对接触时间不确定性更敏感。

**方法学说明**：区间来自"每个目标的接触时间在 [lower, upper] 内任意取值"的保守枚举，A/B 共享同一时间与分母，分子分母联合求极值（`full_metric_domain_core.bounds`）。

---

## 待完成

| 条件 | 状态 |
|---|---|
| clean | ✅ damped vs hold 完成 |
| clean | ⏳ linear_g0500 vs hold 进行中 |
| delay100 / noise100 ×3 / combined100 ×3 | ⏳ 排队中 |

每条件约 3 × 180 s（重放）+ 2 × 240 s（评分）≈ **17 分钟**。
8 条件合计约 **2.2 小时**。

---

## 复现方式

```bash
# 驱动（写入 midterm_batch_v1/）
C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8 -B \
  C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1\p1_v1\midterm_batch_driver_v1.py

# 提取表格
C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8 -B \
  C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1\p1_v1\midterm_extract_v1.py
```

---

## 关键实现约束

1. **不读未来真值**：报警流由 `replay_core.generate` 从冻结观测传感器因果重放，`no_truth_or_contact_labels_read = True`。
2. **不固定旧 valid**：`valid` 由重放得到的 `first` 与接触时间域重新推导。
3. **A/B 共享真值**：同一 `contact_time` 区间、同一 `edge_mask`、同一分母，配对差联合求极值。
4. **不剪 255 边集合**：`edge_mask` 原样传入，未做任何面代码约简。
5. **零分母保留**：`undefined_possible` 字段显式记录。
