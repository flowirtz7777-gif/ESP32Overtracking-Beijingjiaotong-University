# AGENTS.md — Project Context for OpenAI Codex / GitHub Copilot / 通用 AI 编程助手

> 与 `CLAUDE.md` 同步维护；本文件偏向 Codex 风格，列出仓库结构、命令、约定与任务清单。

---

## Section 0 — Autonomy Rules (Highest Priority)

**Execute immediately without asking**: file edits, creates, renames, git add/commit/push, running commands, refactoring, force push, deleting a single file, changes touching credentials/secrets, any PowerShell / shell commands.

**The only operation requiring prior confirmation**: bulk deletion of multiple files or directories (`rm -rf`, `Remove-Item -Recurse`, etc.).

---

## Section 0 — Required Reading: Modeling Philosophy

Above this engineering handbook there is a **top-level design document** defining the project's modeling philosophy, the main-model-vs-baseline argumentation, and the redefined role of the legacy PID model:

📘 **[`预测模型与对照模型构建思路.md`](预测模型与对照模型构建思路.md)** — read first

Key points (must be internalized before making any modeling-related changes):

- This project is fundamentally a **short-horizon risk prediction problem**, not a control problem nor long-term driver-intent recognition.
- "Inner-wheel-difference hazard" is expressed as a **future short-horizon swept area** of the right vehicle edge — not a scalar TF distance.
- Main model = realtime state input + short-horizon coupled-kinematics prediction + danger-zone construction + risk grading.
- Baseline (control) model hierarchy used purely for argumentation (paper / proposal):
  - Baseline 1: PID trajectory generator (conceptual contrast)
  - Baseline 2: static dilated danger band (no prediction)
  - Baseline 3: bicycle / single-body simplification (ignores trailer pose)
- **PID is repositioned**: no longer the final on-board judging model, but a *scenario generator* and *contrast baseline*.

### Top-level Verification Pipeline ⭐

```
                ┌──── Legacy PID Simulation ────┐
                │  Reference heading → PID ctl  │
                │  → emits discrete sequences:  │
                │      v(t), alpha(t), phi(t)   │
                └────────────┬──────────────────┘
                             │
                             │ treat these as if they were
                             │ realtime sensor measurements
                             ▼
                ┌──── New Main Predictor ────────┐
                │  ingest (v, alpha, phi) live   │
                │  → short-horizon coupled       │
                │    kinematics rollout          │
                │  → 3-tier swept polygons       │
                │  → simulated-target risk eval  │
                └────────────┬──────────────────┘
                             │
                             ▼
              compare against PID-simulator ground-truth trajectory
              to validate geometric / temporal correctness
```

This pipeline simultaneously achieves:
- A clean, smooth, controllable input set fed to the main model (PID acts as a virtual driver).
- Full closed-loop validation of the main model **without a physical vehicle**.
- A directly-publishable "Baseline 1 vs Main Model" comparison figure for the paper / proposal.

Trigger this pipeline as soon as Phase 1's `kinematics_step.m` + `predict_swept.m` are in place — it constitutes the first end-to-end gate.

---

## Project Summary

**ESP32-S3 + OpenMV dual-MCU real-time warning system for truck (incl. semi-trailer) right-turn inner-wheel-difference blind-zone hazard.**

- Target hazard: pedestrian / e-bike crushed by trailer rear wheel during right turn
- Approach: rigid-body kinematic prediction + radar + vision sensor fusion
- Output: swept polygon of vehicle right edge over the next T_h seconds, multi-target risk grading, 3-level alarm

---

## Repo Layout

```
.
├── ArduinoIDE/                 # ESP32 firmware (Arduino C++)
│   ├── ESP32TruckOverTrackingWarningSystem.ino
│   ├── config.h
│   ├── sensors_alpha.{h,cpp}   # AS5600 -> alpha (rad)
│   ├── sensors_phi.{h,cpp}     # potentiometer -> phi (rad)
│   ├── speed_can.{h,cpp}       # TWAI -> v (m/s)   [needs decoder]
│   ├── radar_ld2450.{h,cpp}    # HLK-LD2450 -> targets [needs frame parser]
│   ├── utils.{h,cpp}           # LPF, angle unwrap
│   ├── predictor.{h,cpp}       # TODO: kinematics + swept polygon
│   ├── risk_eval.{h,cpp}       # TODO: point-in-poly, TTC
│   ├── alarm_fsm.{h,cpp}       # TODO: 3-level state machine
│   ├── alarm_out.{h,cpp}       # buzzer + LED
│   └── vision_uart.{h,cpp}     # TODO: OpenMV link
├── Matlab/                     # Simulation & algo verification
│   ├── vehicle_params.m        # ✅ vehicle parameter struct
│   ├── kinematics_step.m       # ✅ one-step rigorous kinematics (l_h coupled)
│   ├── derive_points.m         # ✅ derive A/B/H/T from minimal state
│   ├── predict_swept.m         # ✅ 3-tier swept polygon (envelope)
│   ├── point_in_poly.m         # ✅ ray-casting point-in-polygon
│   ├── run_phase1_demo.m       # ✅ Phase-1 top demo: CSV → replay → predict → error report
│   ├── load_pid_scenario.m     # ✅ Read CSV exported by pid工况仿真导出器.html
│   ├── guacheweixianqu.m       # Legacy monolithic semi-trailer sim
│   ├── pid3.m                  # Legacy single-vehicle sim
│   └── (TODO: sim_replay.m / risk_eval.m)
├── OpenMV/                     # TODO: vision coprocessor python
├── overtrack.pdf               # Research / context
├── PCB原理图.png                # Hardware schematic
├── latex代码.txt                # Paper / proposal LaTeX draft
├── 预测模型与对照模型构建思路.md   # 📘 Top-level modeling philosophy
├── pid工况仿真导出器.html         # PID scenario generator (interactive web UI)
├── desktop-main.js              # Optional Electron wrapper for the HTML above
├── package.json                 # Electron build config (node_modules ignored)
├── README.md
├── CLAUDE.md
├── AGENTS.md
└── .gitignore
```

---

## PID Scenario Generator (Phase-1 helper)

To validate the new main predictor before the physical vehicle is available, a
PID-driven scenario generator is bundled in the repo:

| File | Role |
|---|---|
| `pid工况仿真导出器.html` | Standalone web UI: configure vehicle params / reference heading / PID gains, simulate, export discrete CSV `(t, v, alpha, phi, ...)` |
| `desktop-main.js` + `package.json` | Optional Electron desktop wrapper. Run with `npm install && npm run desktop:dev`. Not required — the HTML can be opened directly in any browser. |
| `启动PID工况导出器.bat` | Windows one-click launcher. Double-click to start the Electron desktop wrapper without touching npm or PowerShell. Requires `trae/node_modules/electron/` to be present. |
| `Matlab/load_pid_scenario.m` | MATLAB loader: returns a struct with `params / inputs / states / points / summary` |

**UI design**: Industrial SCADA/HMI control-panel aesthetic with dark/light theme toggle (persisted via `localStorage`). Three launch-method badges displayed at the top (Web / BAT / Desktop shortcut). Standalone single-file HTML, zero external dependencies.

**Recommended Phase-1 workflow**:

```
1. Open  pid工况仿真导出器.html        → tune scenario, click "Export CSV"
   ├─ Electron launcher: save dialog defaults to Matlab/scenarios/
   └─ Plain browser   : downloads to Downloads/, move to Matlab/scenarios/ manually
2. MATLAB:  scenario = load_pid_scenario('pid_scenario_*.csv');
   ├─ filename only   → auto-resolved under Matlab/scenarios/
   ├─ full path       → used as-is
   └─ no argument     → file picker opens at Matlab/scenarios/
3. Treat scenario.inputs.{v_mps, alpha_rad, phi_rad} as virtual sensor data
4. Feed into the new short-horizon predictor and compare swept area against
   scenario.points.{A,B,H,T} (the PID ground truth)
```

**Unified directory**: all PID scenario CSVs live in `Matlab/scenarios/`; both the loader and the Electron exporter default to this path.

**Constraints**:

- The generated CSV is *not* real-world driver data — it is a smooth, controllable
  surrogate. Do not over-claim accuracy in papers based on this alone.
- Never commit `node_modules/`, `package-lock.json`, or `desktop-dist/` (already in `.gitignore`).
- The `trae/` directory (trae IDE sandbox) is also ignored; useful artifacts in it
  are mirrored to the repo root manually when promoted.

---

## Hardware (Combo B)

| Role | Part | Interface |
|---|---|---|
| Master MCU | ESP32-S3-N16R8 | — |
| Vision coproc | OpenMV H7 Plus | UART2 @ 115200 |
| α sensor | AS5600 | I²C or analog (current: ADC pin 34) |
| φ sensor | rotary potentiometer | ADC pin 35 |
| Speed | OBD CAN | TWAI TX=GPIO5 / RX=GPIO4, default 500 kbps |
| Radar | HLK-LD2450 | UART2 RX=16 / TX=17 @ 115200 |
| Buzzer | passive piezo | GPIO12 |
| LED | dual-color | GPIO13 |

Body frame: origin at tractor rear-axle center **B**, x forward, y leftward.

---

## Coding Conventions

### C++ (ESP32 / Arduino)

- C++17, `float` for all physics (ESP32-S3 single-precision FPU)
- Headers: `#pragma once`
- Constants: `static constexpr` in `config.h`, no macros
- Member naming: `_field`, getters `field()`
- Variable naming: include unit suffix — `alpha_rad`, `v_mps`, `x_m`, `phi_rad`
- Serial logs: tag prefix — `[SENS]`, `[PRED]`, `[RISK]`, `[ALRM]`, `[CAN]`
- Avoid `delay()`; non-blocking polling, target main loop @ 50 Hz (`LOOP_DT_MS = 20`)
- No floating point in ISRs

### Python (OpenMV)

- MicroPython subset, no external libs except OpenMV's `sensor`, `image`, `ml`, `pyb`/`machine`
- Default resolution QVGA (320×240); switch to QQVGA when fps drops below 10
- Models in `/sd/model/` or internal flash, `.tflite` int8 quantized
- UART protocol with ESP32 (see below) — fixed binary, never ASCII

### MATLAB

- Use function files, not scripts dumping everything at top level
- Function signatures must mirror C++ counterparts so Codex can move logic in either direction
- Annotate units in comments

### Git

- Commit format: `<type>: <emoji> <summary>` (Chinese summary OK)
  - types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- Branches: `main` (stable), `dev/<topic>`
- Never commit binaries > 50 MB (use cloud storage + link in README)
- Files containing secrets / credentials: never commit

---

## Build / Run

### ESP32 firmware

```bash
# Arduino IDE 2.x (recommended)
# Board: "ESP32S3 Dev Module"
# Flash: 16 MB, PSRAM: OPI 8MB, Partition: Default with PSRAM
# Open: ArduinoIDE/ESP32TruckOverTrackingWarningSystem.ino
# Build & Upload via Arduino IDE GUI
```

### OpenMV firmware

```python
# Open OpenMV IDE -> Tools -> Run script
# Or copy OpenMV/main.py to the camera's USB drive as main.py
```

### MATLAB simulation

```matlab
% Open MATLAB R2021b+, set workspace to repo root
cd Matlab
% Phase 1 entry point (will exist after refactor):
sim_pid                % run with PID-driven inputs
% Or replay real-vehicle CSV:
sim_replay('logs/run_2026-05-26.csv')
```

---

## Core Algorithms

### Kinematics step (with l_h coupling — DO NOT OMIT)

State `s = [xB, yB, theta, phi]`.

```
omega1   = v * sin(alpha) / l            % tractor yaw rate
vB       = v * cos(alpha)
omega2   = ( vB*sin(phi) + l_h*omega1*cos(phi) ) / L   % trailer yaw rate (l_h coupled, rigorous derivation)
vT       =   vB*cos(phi) - l_h*omega1*sin(phi)         % trailer longitudinal speed (informational)

xB     += vB*cos(theta)*dt
yB     += vB*sin(theta)*dt
theta  += omega1*dt
phi    += (omega1 - omega2)*dt           % clamp |phi| <= phi_max

% Straight running (alpha=0, omega1=0): dphi/dt = -vB*sin(phi)/L → phi self-converges to 0
```

Derived points:
```
xA = xB + l*cos(theta),     yA = yB + l*sin(theta)
xH = xB + l_h*cos(theta),   yH = yB + l_h*sin(theta)
theta_t = theta - phi
xT = xH - L*cos(theta_t),   yT = yH - L*sin(theta_t)
```

> WARNING: legacy `guacheweixianqu.m` omits the `l_h*omega1` coupling term in `omega2`.
> Always use the coupled form when refactoring or porting.

### Three-tier swept polygon (per main-loop tick)

| Tier | T_h | dt_pred | meaning |
|---|---|---|---|
| `PolyW` | 2.0 s | 0.05 s | yellow warn |
| `PolyA` | 1.0 s | 0.05 s | red alarm |
| `PolyI` | 0.3 s | 0.05 s | imminent collision |

Right-edge points at each predicted step: take A/B/H/T and offset by +W/2 along right normal:
- A, B, H use **tractor heading** `theta` for normal
- T uses **trailer heading** `theta_t` for normal (this is fixed vs. legacy bug)

Build polygon: `[A_right(0..N)] -> [T_right(N..0)]` closed.

### Risk evaluation (per radar/vision target i)

```
in_imm   = point_in_poly(p_i(0), PolyI)
in_alarm = point_in_poly(p_i(0), PolyA)
in_warn  = point_in_poly(p_i(0), PolyW)
TTC_i    = min tau s.t. point_in_poly(p_i(tau), PolyA)   % CV extrapolation

Risk_i = max:
  in_imm   || TTC_i < 0.3  -> 3
  in_alarm || TTC_i < 1.0  -> 2
  in_warn  || TTC_i < 2.0  -> 1
  else                     -> 0

Risk_total = max_i Risk_i
```

### Alarm FSM (debouncing)

```
upgrade   if condition holds for >= 2 consecutive ticks (40 ms)
downgrade if condition fails for >= 10 consecutive ticks (200 ms)
output:
  S=0  off
  S=1  yellow LED solid
  S=2  red LED solid + buzzer 250ms beep cycle
  S=3  red LED solid + buzzer continuous
```

---

## UART Protocol (OpenMV → ESP32)

Frame:
```
0xAA 0x55 N obj1 ... objN CRC8
each obj: cls(u8) x_mm(i16 LE) y_mm(i16 LE) w_mm(u16 LE) h_mm(u16 LE) conf(u8 0..100)
```
- `cls`: 0=unknown, 1=person, 2=bicycle/e-bike, 3=car
- coords already in body frame (vision module pre-applies extrinsic calibration)
- frame rate target ≥ 10 Hz

---

## Performance Budget (ESP32-S3, 240 MHz, single core)

| Module | Budget |
|---|---|
| sensors + LPF | 0.5 ms |
| predict_swept × 3 tiers | 0.3 ms |
| CV target extrapolation | <0.1 ms |
| point_in_poly × 3 × 3 | 0.2 ms |
| FSM + I/O | <0.1 ms |
| **Total** | **~2 ms** of 20 ms |

Memory: <5 KB heap for polygons + target buffers.

---

## Roadmap & Acceptance Gates

### Phase 1 — MATLAB / C++ kinematics parity (v0.1)

- [ ] `Matlab/vehicle_params.m` with `l, l_h, L, W, phi_max`
- [ ] `Matlab/kinematics_step.m` (signature-match with C++)
- [ ] `Matlab/predict_swept.m`
- [ ] Refactor `guacheweixianqu.m` to use the above
- [ ] `ArduinoIDE/predictor.{h,cpp}`
- [ ] **Gate**: identical input -> polygon vertex error < 1 mm vs. MATLAB

### Phase 2 — Sensor / decoder wiring (v0.2)

- [ ] `speed_can.cpp::speed_mps()` decoder (depends on real CAN dump)
- [ ] `radar_ld2450.cpp::poll()` full LD2450 frame parser
- [ ] α / φ calibration scripts
- [ ] `risk_eval.{h,cpp}` + `alarm_fsm.{h,cpp}` + `alarm_out.{h,cpp}`
- [ ] **Gate**: bench rig — manually rotate α/φ + a reflector, alarm levels transition correctly

### Phase 3 — Vision fusion (v0.3)

- [ ] OpenMV `main.py` with FOMO/MobileNet person model
- [ ] `vision_uart.{h,cpp}` on ESP32 side
- [ ] Spatial calibration (radar/vision extrinsics in `config.h`)
- [ ] Fusion: track association + CV extrapolation
- [ ] **Gate**: targets missed by either sensor get recovered by fusion

### Phase 4 — Vehicle test & docs (v1.0)

- [ ] Low-speed (5–15 km/h) field test, CSV logging
- [ ] Application form, PCB final, user manual
- [ ] Paper / patent draft

---

## Hard Constraints / DO-NOTs

1. **Never** drop the `l_h * omega1` coupling term in trailer kinematics.
2. **Never** assume same heading for tractor and trailer when projecting right-edge — A/B/H use `theta`, T uses `theta_t`.
3. **Never** run heavy ML on ESP32 (model > 100 KB or >1 ms inference).
4. **Never** block main loop with `delay()`. Use `millis()` non-blocking checks.
5. **Never** print all polygon vertices over Serial in main loop (diagnostics only, gated by a flag).
6. **Never** modify kinematics on one side (MATLAB or C++) without mirror-updating the other.
7. **Never** commit ADC raw dumps, video files, or large `.bag` to git (use cloud + link).

---

## Quick Task Hints for AI Assistants

When asked to:
- "**修运动学**" / "**fix kinematics**" → see Phase 1 + the coupled form above
- "**加视觉**" / "**add vision**" → start with OpenMV `main.py` + UART protocol
- "**调报警**" / "**tune alarm**" → modify `alarm_fsm.cpp` thresholds in `config.h`, not code
- "**生成报告**" / "**generate report**" → use `latex代码.txt` template + `MATLAB` figures
- "**移植算法**" / "**port algorithm**" → MATLAB function `f.m` ↔ C++ `f()`, keep signatures identical

For any change touching `predictor.{h,cpp}` or `kinematics_step.m`, update **both** sides and add a unit-test-style cross-check in Phase 1.

---

## Reference Documents (in repo root)

- `overtrack.pdf` — overall research summary
- `内轮差.pdf` — domestic engineering reference
- `车辆转弯时内轮差的运动学理论模型.pdf` — primary kinematics reference
- `铰链车右转内轮差区域范围确定方法_李英帅.pdf` — Li Yingshuai paper, basis of TF inner-wheel-diff definition
- `附件1~5.pdf/docx/xlsx` — Beijing Jiaotong University 2026 challenge cup official forms
