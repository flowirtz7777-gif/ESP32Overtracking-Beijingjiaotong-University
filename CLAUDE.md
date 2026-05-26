# CLAUDE.md — 项目上下文 (面向 Claude Code / Cursor / Anthropic 系列)

> 此文件用于让 AI 编程助手理解本项目的目标、架构与约定。
> 与 `AGENTS.md` 内容保持同步，区别仅在于面向不同工具。

---

## 1. 项目一句话

**ESP32-S3 + OpenMV 双 MCU 架构的货车（含半挂车）右转内轮差实时预警系统。**

输入：前轮转向角 α、铰接角 φ、车速 v、毫米波雷达目标、视觉行人检测框
输出：未来 T_h 秒车身右侧扫掠多边形 + 多目标分级风险 + 三级报警

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
├── vehicle_params.m       # 车型参数 struct
├── kinematics_step.m      # 一步运动学（与 C++ 移植对照）
├── predict_swept.m        # 在线扫掠多边形预测
├── risk_eval.m            # 风险等级算子
├── sim_pid.m              # PID 仿真台架（生成测试输入）
├── sim_replay.m           # 实测 csv 回放
└── guacheweixianqu.m      # 历史一体化脚本（逐步重构）
```

---

## 4. 核心算法（关键，必须理解）

### 4.1 严格运动学（含鞍座偏置 l_h 耦合）

状态 `s = [xB, yB, θ, φ]`：

```
ω1     = v · sin(α) / l                   // 牵引车横摆率
vB     = v · cos(α)
v_Hxt  =  vB·cos(φ) + l_h·ω1·sin(φ)       // 鞍座 H 在挂车体系下纵向速度
v_Hyt  = -vB·sin(φ) + l_h·ω1·cos(φ)
ω2     = v_Hyt / L                        // 挂车横摆率
vT     = v_Hxt

xB    += vB·cos(θ)·dt
yB    += vB·sin(θ)·dt
θ     += ω1·dt
φ     += (ω1 − ω2)·dt    并约束 |φ| ≤ φ_max
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

每个雷达 / 视觉目标 i：
```
in_imm   = point_in_poly(p_i(0), PolyI)
in_alarm = point_in_poly(p_i(0), PolyA)
in_warn  = point_in_poly(p_i(0), PolyW)
TTC_i    = 首次 point_in_poly(p_i(τ), PolyA) 的 τ

Risk_i = max:
  in_imm   || TTC_i < 0.3 → 3
  in_alarm || TTC_i < 1.0 → 2
  in_warn  || TTC_i < 2.0 → 1
  否则                   → 0

Risk_total = max_i(Risk_i)
```

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
