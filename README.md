# ESP32 货车内轮差预警系统 (Truck Overtracking Warning System)

> 北京交通大学 2026 "挑战杯" 大学生创业计划竞赛 / 大学生创新创业训练计划项目

针对中重型货车（含半挂车）右转过程中，因**内轮差盲区**导致行人/电动车被卷入的事故场景，设计一套基于车辆运动学预测 + 雷达 + 视觉融合的实时预警系统。

## 系统总览

```
┌─── 输入 ──────────────────┬─── 内参 ─────────────┐
│  v   牵引车纵向速度 (CAN)   │  l    牵引车轴距          │
│  α   前轮转向角 (AS5600)    │  l_h  后悬长 (B→H)        │
│  φ   铰接角 (电位计)        │  L    挂车轴距 (H→T)      │
│  雷达目标 (LD2450)          │  W    车宽                │
│  视觉目标 (OpenMV H7)       │  雷达/相机安装偏置        │
├──────────────────────────────────────────────────────┤
│              输出 (Outputs)                           │
│  PolyR(t)  右侧车身扫掠多边形（T_h 秒预测）           │
│  Risk[i]   每个目标的风险等级 ∈ {0,1,2,3}            │
│  Alarm     蜂鸣 + LED 三级报警                        │
└──────────────────────────────────────────────────────┘
```

## 硬件方案（组合 B：ESP32 + OpenMV 双 MCU）

| 角色 | 型号 | 用途 |
|---|---|---|
| 主控 | ESP32-S3-N16R8 | 传感器融合、运动学预测、风险评估、报警决策 |
| 视觉协处理器 | OpenMV H7 Plus | 行人/电动车检测，UART 输出检测框给主控 |
| α 传感器 | AS5600 | 前轮转向角 |
| φ 传感器 | 角度电位计 | 铰接角 |
| 速度 | CAN OBD | 整车纵向速度 |
| 雷达 | HLK-LD2450 | 右侧 0-6m 范围目标位置/速度 |

## 仓库结构

```
.
├── ArduinoIDE/          # ESP32 主控固件 (Arduino IDE, C++)
├── Matlab/              # 仿真与算法验证 (.m)
├── overtrack.pdf        # 项目调研材料
├── PCB原理图.png         # 硬件原理图
├── latex代码.txt         # 论文/申报书 LaTeX 草稿
├── CLAUDE.md            # AI 编程助手 (Claude/Cursor) 项目指南
├── AGENTS.md            # AI 编程助手 (Codex / OpenAI) 项目指南
├── README.md            # 本文件
└── .gitignore
```

## 开发路线

- **Phase 1 (v0.1)**: MATLAB 几何仿真 + ESP32 几何预警 baseline
- **Phase 2 (v0.2)**: 加 OpenMV 视觉协处理器，雷达-视觉融合
- **Phase 3 (v0.3)**: 加驾驶员意图预测 GRU、三级报警状态机
- **Phase 4 (v1.0)**: 实车低速测试，完整文档 + 申报书

详见 [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md)。

## 协作约定

- 给 AI 编程助手的项目上下文写在 `CLAUDE.md` (Claude/Cursor) 和 `AGENTS.md` (Codex/Copilot) 里，二者内容保持同步
- 所有提交信息使用中文 + emoji 前缀（`feat: ✨` / `fix: 🐛` / `docs: 📝` / `refactor: ♻️`）
- 默认编辑器文件 UTF-8，Windows 下 `git config core.autocrlf input`
