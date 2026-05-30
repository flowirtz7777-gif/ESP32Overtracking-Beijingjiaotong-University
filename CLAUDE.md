# CLAUDE.md — 项目上下文 (面向 Claude Code / Cursor / Anthropic 系列)

> 此文件用于让 AI 编程助手理解本项目的目标、架构与约定。
> 与 `AGENTS.md` 内容保持同步，区别仅在于面向不同工具。

---

## 0. 操作权限约定（最高优先级）

**直接执行，不需要询问**：文件编辑、新建、重命名、git add/commit/push、运行命令、重构代码、force push、删除单个文件、改动密钥/凭证相关内容、任何 PowerShell / shell 命令。

**唯一需要事先确认的操作**：批量删除多个文件或目录（`rm -rf`、`Remove-Item -Recurse` 等)。

**Release 后写复盘的强制约定**：每打一个 `vX.Y.Z` tag 后，必须在 `工作复盘/` 目录新增一份 `vX.Y.Z_<主题>.md`，按 `工作复盘/README.md` 的模板写。复盘文件一旦提交不再修改，作为该版本的工程档案快照。

---

## 0. 必读 — 项目建模哲学（顶层文档）

本工程执行手册之上还有一份**顶层论证文档**，定义了项目的建模哲学、主模型与对照模型的论证体系、PID 模型的重新定位等核心思想：

📘 **[`预测模型与对照模型构建思路.md`](预测模型与对照模型构建思路.md)** — 必读

文档要点（执行任何修改前都应理解）：

- 本项目本质是**"短时风险预测问题"**，不是控制问题，也不是长时驾驶意图理解
- 内轮差危险 = **未来短时车身右侧扫掠区域**（不是单个标量 TF 距离）
- 主模型 = 实时状态输入 + 短时耦合运动学预测 + 危险区构造 + 风险判定
- 对照模型体系（用于论文/申报书论证主模型必要性）：
  - 对照 1：PID 轨迹生成模型（思维对照）
  - 对照 2：静态扩张危险带模型（无预测能力基线）
  - 对照 3：简化单车模型（忽略挂车姿态）
- **PID 模型重新定位**：不再是最终判警模型，而是"工况生成器 + 对照模型"

### 顶层验证套路 ⭐

```
                ┌────── 旧 PID 仿真 ──────┐
                │  生成参考航向 → PID 控制 │
                │  → 输出离散序列:        │
                │    v(t), α(t), φ(t)     │
                └─────────────┬───────────┘
                              │
                              │ 把这些离散序列当作"测量数据"
                              ▼
                ┌────── 新主预测系统 ──────┐
                │  以 (v,α,φ) 为实时输入   │
                │  → 短时耦合运动学预测     │
                │  → 三层扫掠危险多边形    │
                │  → 模拟雷达目标判内       │
                └─────────────┬───────────┘
                              │
                              ▼
                  与"旧 PID 仿真真值轨迹"对比
                  验证预测系统的几何/时序正确性
```

这条验证链同时实现了：
- 给主模型一组干净、平滑、可控的输入工况（PID 充当虚拟司机）
- 让主模型在没有真车的前提下完成自洽性 + 几何正确性验证
- 自然形成"对照模型 1 vs 主模型"的对比图表，可直接进论文

实施时机：Phase 1 完成 `kinematics_step.m` + `predict_swept.m` 后，即用此套路做第一次完整闭环验证。

---

## 1. 项目一句话

**ESP32-S3 + OpenMV 双 MCU 架构的货车（含半挂车）右转内轮差实时预警系统。**

输入：前轮转向角 α、铰接角 φ、车速 v、毫米波雷达目标、视觉行人检测框
输出：未来 T_h 秒车身右侧扫掠多边形 + 多目标分级风险 + 三级报警

---

## 1.5 PID 工况生成器（Phase-1 辅助工具，与 AGENTS.md 同步）

为在无真车条件下验证主预测器，仓库中提供一组 PID 驱动的工况生成工具：

| 文件 | 角色 |
|---|---|
| `pid工况仿真导出器.html` | 独立网页：配置车辆参数 / 参考航向 / PID 增益，仿真后导出离散 CSV `(t, v, α, φ, ...)` |
| `desktop-main.js` + `package.json` | 可选 Electron 桌面壳。`npm install && npm run desktop:dev` 即可启动。**非必需**——HTML 双击就能用 |
| `启动PID工况导出器.bat` | Windows 一键启动器，双击直接打开 Electron 版导出器，免开 PowerShell / 免敲 npm。依赖 `trae/node_modules/electron/` 存在 |
| `Matlab/load_pid_scenario.m` | MATLAB 加载脚本：返回 `params / inputs / states / points / summary` 分组 struct |

**UI 设计**：工业 SCADA/HMI 控制台风格，支持深色/浅色主题切换（`localStorage` 持久化），右上角工业翘板开关控制。页面顶部展示三种启动入口徽章（Web / BAT / 桌面快捷方式）。纯单文件 HTML，无外部依赖。

**Phase 1 工作流**：

```
1. 打开 pid工况仿真导出器.html       → 调参，点击"导出 CSV"
   ├─ Electron 启动器：保存对话框默认指向 Matlab/scenarios/
   └─ 浏览器直开：下载到默认 Downloads，需手动移到 Matlab/scenarios/
2. MATLAB: scenario = load_pid_scenario('pid_scenario_*.csv');
   ├─ 仅传文件名 → 自动到 Matlab/scenarios/ 找
   ├─ 传完整路径 → 直接用
   └─ 不传参数  → 弹文件框，默认打开 Matlab/scenarios/
3. 把 scenario.inputs.{v_mps, alpha_rad, phi_rad} 当作虚拟传感器数据
4. 喂给新主预测器，与 scenario.points.{A,B,H,T} 真值轨迹对比扫掠区域
```

**统一目录约定**：所有 PID 工况 CSV 集中在 `Matlab/scenarios/`，loader 默认查找该路径，Electron 导出默认存该路径。

**约束**：

- 该 CSV **不是**真车数据，是平滑可控的替身。论文里别仅凭它声称真实精度
- `node_modules/`、`package-lock.json`、`desktop-dist/` 永远不进 git（已在 `.gitignore`）
- `trae/` 目录是 trae IDE 沙箱，也已忽略；里面的产物升级到正式版时手动复制到仓库根

---

## 2. 硬件架构（组合 B）

```
┌──────────────── 主控 (Arduino IDE, C++) ────────────────┐
│  ESP32-S3-N16R8                                          │
│   ├─ AS5600 (I²C/ADC) ────── α 前轮转向角                │
│   ├─ 角度电位计 (ADC) ─────── φ 铰接角                    │
│   ├─ MCP2515 / TWAI ──────── CAN 车速 v                  │
│   ├─ HLK-LD2450 (UART) ───── 毫米波目标 (x,y,vx,vy)      │
│   ├─ UART2 ───────────────── ⇄ OpenMV (视觉框)          │
│   ├─ Buzzer (PWM) ────────── 蜂鸣器                       │
│   └─ Dual-color LED ──────── 状态指示                     │
├──────────────── 视觉协处理器 (OpenMV IDE, Python) ─────┤
│  OpenMV H7 Plus                                          │
│   ├─ 自带 OV5640 摄像头 ────── 车身右侧前方               │
│   ├─ FOMO/MobileNet 行人检测                             │
│   └─ UART → ESP32-S3                                     │
└──────────────────────────────────────────────────────────┘
```

车体坐标系约定：原点取**牵引车后轴中心 B**，x 指向车头，y 指向左侧。
所有外部传感器数据（雷达、视觉）先做 `(x0, y0, θ0)` 偏置变换到车体系再参与判内。

---

## 3. 软件架构

### 3.1 ESP32 端（C++ / Arduino）

```
ArduinoIDE/
├── ESP32TruckOverTrackingWarningSystem.ino   # 主入口，调度循环
├── config.h                                   # 引脚 / 车型参数 / 阈值
├── sensors_alpha.{h,cpp}                      # AS5600 → α (rad)
├── sensors_phi.{h,cpp}                        # 电位计 → φ (rad)
├── speed_can.{h,cpp}                          # CAN 解析 → v (m/s)
├── radar_ld2450.{h,cpp}                       # LD2450 帧解析 → 目标列表
├── utils.{h,cpp}                              # LPF / 角度 unwrap
│
├── predictor.{h,cpp}                          # ★ 运动学预测 + 扫掠多边形
├── risk_eval.{h,cpp}                          # ★ 多边形判内 + TTC
├── alarm_fsm.{h,cpp}                          # ★ 三级报警状态机
├── alarm_out.{h,cpp}                          # 蜂鸣 + LED 输出
└── vision_uart.{h,cpp}                        # ★ 与 OpenMV 通信
```

带 ★ 的是后续要新增的核心模块。

### 3.2 OpenMV 端（Python / MaixPy 风格 OpenMV API）

```
OpenMV/
├── main.py                # 启动加载模型 + 主循环
├── detector.py            # 模型加载与推理封装
├── tracker.py             # 简单跨帧 ID 跟踪
└── uart_proto.py          # 与 ESP32 通信协议
```

视觉协议（UART, 115200 8N1）单帧格式：
```
0xAA 0x55 [N] [obj1: cls(1) x(2) y(2) w(2) h(2) conf(1)] ... [CRC8]
```
单位 mm（图像坐标 → 标定后近似车体系）。

### 3.3 MATLAB 仿真（地面真值 / 算法验证）

```
Matlab/
├── vehicle_params.m       # ✅ 车型参数 struct（与 C++ VehicleParams 对齐）
├── kinematics_step.m      # ✅ 一步严格运动学（含 l_h 耦合）
├── derive_points.m        # ✅ 从最小状态派生 A/B/H/T 几何点
├── predict_swept.m        # ✅ 三层扫掠多边形（包络法）
├── point_in_poly.m        # ✅ 射线法判内
├── run_phase1_demo.m      # ✅ Phase 1 顶层 demo：CSV → 回放 → 预测 → 误差报告
├── load_pid_scenario.m    # ✅ 读取 pid工况仿真导出器.html 导出的 CSV
├── sim_pid.m              # 待办：PID 仿真台架（生成测试输入）
├── sim_replay.m           # 待办：实测 csv 回放
├── risk_eval.m            # 待办：风险等级算子（多边形+目标→Risk）
├── pid3.m                 # 历史：单车 PID 仿真
└── guacheweixianqu.m      # 历史：半挂车 PID + 扫掠区一体化（已识别 4 处问题，待删）
```

**Phase 1 一键跑**：

```matlab
out = run_phase1_demo();         % 弹文件框选 CSV（默认目录 Matlab/scenarios/）
% 或
out = run_phase1_demo('pid_scenario_*.csv');
```

输出三幅图 + 误差报告；通过门控 = `out.pass_gate == true`（位置最大误差 < 1mm）。
**自动归档**：每次执行会在 `Matlab/runs/<时间戳>__<csv名>/` 下保存三张 PNG + summary.txt。

**时间尺度速查表**（与代码常量一致）：

| 多边形 | T_h（预测窗口） | 含义 | 在 5/10/15 m·s⁻¹ 下纵向覆盖 |
|---|---|---|---|
| `PolyW` | 2.0 s | 黄色警告 | ~10 / 20 / 30 m |
| `PolyA` | 1.0 s | 红色报警 | ~5 / 10 / 15 m |
| `PolyI` | 0.3 s | 立即危险 | ~1.5 / 3 / 4.5 m |

- 预测内部积分步长 `dt_pred = 0.05 s`（每 T_h 切 N 段）
- ESP32 主循环 `LOOP_DT_MS = 20 ms / 50 Hz` → 每 20ms 重做一次完整 predict + 判内
- 多边形横向宽度 = 车宽 W（约 2.5 m），从车身右外侧 +W/2 起延伸

---

## 4. 核心算法（关键，必须理解）

### 4.1 严格运动学（含鞍座偏置 l_h 耦合）

状态 `s = [xB, yB, θ, φ]`：

```
ω1     = v · sin(α) / l                   // 牵引车横摆率
vB     = v · cos(α)
ω2     = ( vB·sin(φ) + l_h·ω1·cos(φ) ) / L   // 挂车横摆率（含 l_h 耦合，严格推导）
vT     =   vB·cos(φ) - l_h·ω1·sin(φ)         // 挂车纵向速度（备用）

xB    += vB·cos(θ)·dt
yB    += vB·sin(θ)·dt
θ     += ω1·dt
φ     += (ω1 − ω2)·dt    并约束 |φ| ≤ φ_max

// 直行时 α=0, ω1=0  →  dφ/dt = -vB·sin(φ)/L  →  φ 自然回正
```

派生（不是独立状态）：
```
xA = xB + l·cos(θ),     yA = yB + l·sin(θ)
xH = xB + l_h·cos(θ),   yH = yB + l_h·sin(θ)
θ_t = θ - φ
xT = xH - L·cos(θ_t),   yT = yH - L·sin(θ_t)
```

> ⚠️ **重要**：旧版 `guacheweixianqu.m` 漏了 `l_h·ω1` 耦合项，导致 φ 演化失真。
> 重构时务必使用新公式。

### 4.2 三层扫掠多边形

每个主循环（50Hz）从当前状态 `s0` 向前推三档：

| 区域 | T_h | dt | 用途 |
|---|---|---|---|
| PolyW (warn) | 2.0 s | 0.05 s | 黄色警告 |
| PolyA (alarm) | 1.0 s | 0.05 s | 红色报警 |
| PolyI (immediate) | 0.3 s | 0.05 s | 立即危险 |

α 外推假设：
- v0.1：`α(τ) = α_now`（保持不变）
- v0.2：`α(τ) = α_now + α̇_now · τ`（线性外推）
- v0.3+：用驾驶员意图小型 GRU 预测

每条边沿轨迹（A_right, B_right, H_right, T_right）取右侧法向 +W/2 投影，时序 + 末端 + 反序闭合成多边形。

### 4.3 风险评估

#### 在线主判警口径（必须保持）

在线实车端只能使用当前传感器输入 `(v, alpha, phi)` 做短时预测，不能使用 CSV 后验真值轨迹反推。主判警逻辑保持：

1. 先判当前挂车车身占用区 `BodyNow`。若目标中心点已经落入当前 `H-T` 挂车矩形投影内，直接 `Risk_i = 3`。
2. 若未命中 `BodyNow`，再按 `predict_swept` 输出的三层预测多边形 `PolyI / PolyA / PolyW` 判目标中心点。
3. 后验 true TTC 只能用于 MATLAB/Python 复盘评估，不得替代在线主判警。

`BodyNow` 构造方式：

```
d = derive_points(s, p)
right_normal = [sin(d.theta_t), -cos(d.theta_t)]
BodyNow = [
  H + W/2 * right_normal
  T + W/2 * right_normal
  T - W/2 * right_normal
  H - W/2 * right_normal
]
```

此兜底用于修复“目标已经被右外缘扫过、当前位于挂车车身内部，但未来外缘扫掠多边形不再覆盖它”的漏判。`Matlab/run_phase1_demo.m` 已实现此逻辑；后续 `ArduinoIDE/risk_eval.{h,cpp}` 必须同步实现。

每个雷达 / 视觉目标 i：
```
in_body = point_in_poly(p_i(0), BodyNow)
in_imm   = point_in_poly(p_i(0), PolyI)
in_alarm = point_in_poly(p_i(0), PolyA)
in_warn  = point_in_poly(p_i(0), PolyW)
TTC_i    = 首次 point_in_poly(p_i(τ), PolyA) 的 τ

Risk_i = max:
  in_body                 → 3
  in_imm   || TTC_i < 0.3 → 3
  in_alarm || TTC_i < 1.0 → 2
  in_warn  || TTC_i < 2.0 → 1
  否则                   → 0

Risk_total = max_i(Risk_i)
```

#### 复盘口径（不要搬到在线端）

`Matlab/truck_slider_sim.py` 是 TTC 复盘/可视化程序：它读取已导出的完整 CSV 真值轨迹，用未来真实车身占用来计算 true TTC、检查 Poly 判警是否过晚。它可以揭示 R3 这类“真实还有 2 秒但当前恒定 alpha 预测尚未覆盖”的提前量问题，但它不是实车在线算法。

#### R3 报警偏晚问题（必须记住）

`pid_scenario_20260530_020804.csv` 中 R3 是当前最重要的复盘反例：

```
R3 = (15.162112188, 34.264469347)
真实挂车车身覆盖时间 ≈ 16.24 s - 18.12 s

t = 14.24 s: true TTC ≈ 2.00 s
t = 15.24 s: true TTC ≈ 1.00 s
t = 16.00 s: true TTC ≈ 0.24 s
```

当前在线预测默认 `alpha(τ)=alpha_now`。该假设稳定、适合早期硬件实现，但在弯道后段 / 转向角快速回正阶段可能低估后续挂车右侧车身外缘（尤其前中段）的扫掠趋势，导致 R3 这类目标的 Poly 首次报警偏晚。驾驶员/系统反应时间叠加后，首次高等级报警可能已经不足以避免碰撞。

不要把这个问题粗略描述成“挂车尾部扫到人”。半挂车转弯时后轴/尾部常相对弯心外甩，远离内轮差危险区；更典型的内侧挤压来自 H 到挂车中部一带的右侧车身外缘向弯心内侧切入。尾部是否会扫到目标取决于目标位置与外甩方向，不能一概而论。

注意边界：
- 不要把后验 true TTC 当作在线算法输入；实车没有完整未来真值轨迹。
- R3 复盘用于评估“当前 poly 主算法提前量是否足够”，不是替代 `predict_swept`。
- 后续改进应优先做：低通后的 `alpha_dot` 短时外推、与 `alpha_dot=0` 分支取并集、目标宽度/安全半径膨胀、批量复盘统计 true TTC 与 poly 首次报警时间差。

### 4.4 报警状态机（滞回防抖）

```
S = 当前等级 ∈ {0,1,2,3}
连续 N_up=2 次（40ms）满足升级条件 → 升级
连续 N_down=10 次（200ms）不满足 → 降级一档
```

---

## 5. 性能预算（ESP32-S3 单核）

| 模块 | 单次耗时 |
|---|---|
| 传感器读取 + 滤波 | ~0.5 ms |
| `predict_swept` × 3 层 | ~0.3 ms |
| 目标 CV 外推 | <0.1 ms |
| `point_in_poly` × 3 层 × 3 目标 | ~0.2 ms |
| 状态机 + 输出 | <0.1 ms |
| **合计** | **~2 ms** （20ms 周期，富余 90%）|

内存：3 层多边形 + 雷达/视觉缓冲 < 5 KB（占 ESP32-S3 SRAM <2%）

---

## 6. 编码约定

### C++ (ESP32)

- 全局参数集中在 `config.h`，用 `static constexpr` 而非宏
- 浮点统一 `float`（ESP32-S3 单精度 FPU），避免 `double`
- 避免在中断里做浮点
- 头文件用 `#pragma once`
- 类成员变量前缀 `_`（如 `_phi_unwrapped`）
- 物理量命名：`alpha_rad` / `phi_rad` / `v_mps` / `pos_x_m` 显式带单位
- 串口诊断打印加 tag：`[SENS]` `[PRED]` `[RISK]` `[ALRM]`

### Python (OpenMV)

- 图像分辨率默认 QVGA (320×240)，必要时降到 QQVGA 提帧率
- 模型放 `/sd/model/` 或内置 flash
- 与 ESP32 通信用 `struct.pack` 固定字节序

### MATLAB

- 一律使用函数文件而非脚本里堆代码
- 物理量带单位注释，与 C++ 对齐
- `kinematics_step.m` 输入输出签名要与 C++ `Predictor::step` **完全一致**，方便交叉验证

### Git

- 提交信息：`类型: emoji 简述`，类型 ∈ {feat, fix, refactor, docs, test, chore}
- 默认分支 `main`，开发用 `dev/<feature>` 分支
- 大于 50MB 的二进制（视频、bag 等）不进仓库，放云盘并在 README 给链接

---

## 7. 开发优先级（给 AI 助手的执行顺序）

修改代码时，遵循以下优先级与门控：

### Phase 1 (v0.1) — MATLAB → C++ 等价移植

1. 写 `Matlab/vehicle_params.m`、`Matlab/kinematics_step.m`
2. 重构 `guacheweixianqu.m`，使用新运动学函数（含 `l_h` 耦合）
3. 写 `Matlab/predict_swept.m`，输出三层多边形
4. 写 `ArduinoIDE/predictor.{h,cpp}`，与 MATLAB 字字对照
5. **验收门控**：相同输入下，C++ 输出顶点与 MATLAB 误差 < 1 mm

### Phase 2 (v0.2) — 硬件接口闭环

6. `speed_can.cpp`：补 `speed_mps()` 解码
7. `radar_ld2450.cpp`：补完整帧解析 + Kalman 平滑 (vx, vy)
8. α / φ 标定接口：直行零位 + 90° 增益
9. 加 `risk_eval.{h,cpp}` + `alarm_fsm.{h,cpp}` + `alarm_out.{h,cpp}`
10. **验收门控**：桌面台架（手动转 α/φ + 反射板）能正确升降级

### Phase 3 (v0.3) — 视觉融合

11. OpenMV 端跑 `person_detection.tflite`，UART 输出 box 列表
12. ESP32 写 `vision_uart.{h,cpp}` 解析协议
13. 雷达-视觉时空配准（坐标统一 + 时间戳对齐）
14. 联合 CV 外推 + 一致性融合
15. **验收门控**：视觉/雷达单独漏检的目标，融合后能补回

### Phase 4 (v1.0) — 实车与文档

16. 实车低速 (5–15 km/h) 路试，CSV 数据回放
17. 完成申报书、PCB 设计、用户手册
18. 论文/专利材料整理

---

## 8. 不要做的事

- ❌ 在 ESP32 端跑大模型（参数 > 100KB），算力撑不住，且认证不利
- ❌ 替换运动学方程为神经网络（确定性模型已最优）
- ❌ 在 ESP32 主循环内做 `printf` 输出多边形所有顶点（容易堵串口）
- ❌ 使用 `delay()` 阻塞主循环
- ❌ 在中断里调用浮点函数 / `Serial.print`
- ❌ 直接从 OpenMV 摄像头到雷达坐标系做大量浮点变换（应在 ESP32 上做）
- ❌ 修改既有运动学公式时不同步更新 MATLAB 与 C++ 两端（必须配对修改）
- ❌ **BAT 启动器写中文路径不要直接用 cmd if exist**：cmd.exe 默认 GBK 解码，UTF-8 BAT 会乱码，GBK BAT 又不能跨 IDE 编辑。**正确做法**：BAT 只做一行 `powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"`，所有路径逻辑放进 launch.ps1（PowerShell 原生 Unicode 安全）。当前实现见 `TTC预警复盘软件/launch.ps1` + `启动TTC预警复盘软件.bat`。

---

## 9. 当前进度（v0.0 → v0.1）

- ✅ ESP32 工程骨架（含 α/φ/CAN/雷达字节流统计）
- ✅ MATLAB PID 仿真（单车 + 半挂车，但运动学待修正）
- ✅ PCB 原理图初版
- 🚧 运动学含鞍座偏置耦合的重构
- 🚧 三层扫掠多边形 + 在线预测
- ⏳ OpenMV 视觉协处理器
- ⏳ 三级报警与风险融合

---

## 10. 联系点

竞赛通知与申报材料：仓库根目录 `附件1/2/3/4/5*.pdf` 与 `*.docx`。
学术参考：`内轮差.pdf` / `车辆转弯时内轮差的运动学理论模型.pdf` / `铰链车右转内轮差区域范围确定方法_李英帅.pdf`。
