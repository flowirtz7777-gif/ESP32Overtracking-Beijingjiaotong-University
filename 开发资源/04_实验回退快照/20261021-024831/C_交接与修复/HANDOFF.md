# 自动化实验：上下文恢复交接

本次迁移由人类在 2026-10-20 的“检查另一个对话状态”对话中明确批准“可以，你改一下”。这是既有任务的接续，不增加研究范围、预算或期限。旧对话“自动化实验”019ebf60-7584-7591-980b-75cc8eea8471保留；旧线程连续 remote compact / context window exceeded，不再向它重试。不要 fork 全部旧历史。

## 路径与读入顺序

- 研究 ROOT：Z:\大创内轮差项目_实验结果\科研实验_2026-10-14
- E_ROOT（只读）：E:\大创内轮差项目\工具\转弯全过程盲区分析软件\科研实验_2026-10-14
- AUTH（相对 ROOT）：runs/resume_20261022_0000_truth_authorization_v1
- 本交接目录：C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1
- 每次先读本文件和本目录 STATUS.md，然后 ROOT/active_research_run.json、按版本整数排序的最新 resume_plan_20261022_0000_v*.json。它们的 running/PID 字段可能过时，不能直接判活。
- 初次恢复还须读本目录 current_stage_from_original_prompt.md，以及 ROOT/reports/10月20日续研授权与32GiB资源边界_v1.md、AUTH/authorization.json、当前 protocol_unwitnessed_probe_20261022_0000_v1.json、当前父依赖与执行登记。最新阶段优先于历史“下一优先”。
- 原完整约束与所有历史科学阶段、失败、哈希、单次入口使用记录均无损保存在本目录 original_heartbeat_instructions.md、automation-2.before.toml/json；有疑问时按关键词定向读取，禁止每次全量重复塞入对话。不要丢弃任何未定或失败记录。

## 硬边界（保持原授权）

1. 授权至北京时间 2026-10-22 00:00（2026-10-21 16:00 UTC，10月21日24点），不自动续期。到期后不再新提交科学分析、预测、输入构建或科学 close；已提交块自然结束保存断点，实际退出后仅行政收尾。以实时钟检查期限，不能依据旧消息时间。
2. E 全部只读。E+Z 两个研究目录合计上限 32 GiB，Z 物理预留至少 3 GiB。单科学 worker、一次在途，BLAS 单线程。每次写前全量 fresh scandir 资源核验，载荷先 RAM 无损编码计量；不得改旧 run cap 或绕过资源/进程守卫。
3. 全部冻结源、协议、输入、结果、失败、封存不删改、不搬移。旧 prepare/launch/run/close 入口是否已用，必须按原阶段证据核实；已用入口禁止重跑。任何科学改动另建新冻结版本、合成测试、完整父依赖准入和独立 close。禁止临时 python -c 真实分析。
4. 所有 shell 显式 workdir C:\Users\Admin（旧 Desktop cwd 可能无效）。Python 精确使用 C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8 -B。E 项目可作为任务归属，但不得写入 E。
5. 判活必须联合核实际精确命令行、runner/analysis 锁、Local\InnerWheelResearch20261014 mutex、追加日志；历史 PID 与 active 状态不算证据。活动 checkpoint 禁止读取或 hash，不做活动 CP 全 E/Z 快照。科学 close 运行期间不要另开含 ROOT 命令行的外部监视 shell，以免触发原进程守卫。不得改守卫或冒用监视器名称。
6. 未知、预算耗尽、冲突完整保留，不能当负例；不按算法表现选点或择赢家。完整首次接触前缀与全部原序投影、全部必要父依赖都须核实。空间经验界不是形式区间 ODE 或实车证书。
7. 科学阈值、角点、空间误差和可靠性门保持原值，不因进度放宽（含 0.2 个百分点/0.05 秒、5% 点误报/0.5% 帧误报）。旧 RIGHT/FRONT/接触时间/混淆/零漏报/排名/84配置可行性与部署安全推荐继续暂停。修正真值重验预测 0；S4 整体、M2、S5 未完成，M2/S5 不准入。相关性/机器学习/贝叶斯寻优仅概念规划，未授权实际训练或搜索。

## 迁移时实际观察（不是科学验收）

- 磁盘 active 指向 v30：runs/resume_20261022_0000_unwitnessed_probe_v1；entrypoint 为 src_s4_unwitnessed_probe_20261022_v1/probe_driver.py。
- 原 worker 35624 已完成候选计算，stdout 末尾为 `UNWITNESSED PROBE WORKER EXITING; candidate acceptance and merge pending`，stderr 空。runner_lock.json 为 stopped，时间 2026-10-20T08:34:25+00:00，即北京时间16:34:25。
- 本恢复会话实际进程列表仅看到另外项目 Label Studio 的两个 Python，没有该科学 worker。探测命名 mutex 时对象不存在（不宣称已取得并释放，不为伪造证据新建锁）。新对话必须重新独立核实。
- 当前 run 顶层仅观察到 checkpoint.json、dependency_files_sha256.json、preflight.json、prelaunch.json、runner_lock.json、source_manifest.json；未观察到 acceptance、close_receipt 或 analysis_lock。此时没有读取/hash checkpoint。close 未用的历史记录来自原提示，仍须独立核对。
- active 仍写 running_analysis=true 和 PID35624，v30 plan 还写 prepared_not_admitted，这些均滞后，不能代表 worker 仍运行或未准入；禁止直接改写冻结计划来掩盖状态差异。
- 当前完整 scope 的父 census（来自磁盘 active/v30，尚未重新科学核验）：57文件/39组/3360000分文件点记录；未知完整范围26878分文件点记录、22857组内唯一点；combined status unknown13956。原因重叠，不能相加为独立样本。v30 是候选，尚未独立验收、合并或提升真值。

## 恢复后的顺序

首次接入只读核对路径、时钟、期限、实际进程/锁/mutex、日志和已保存文档，用简短回复完成一轮健康验证；不启动科学 close 或新 worker，不改研究文件。等待调度器接续，避免迁移期间重复执行。

健康验证后按原授权接续：先核当前 v30 的完整停止 CP、全部已用入口、父依赖、资源和科学 close 是否已尝试；若确证 close 未用、完整性准入满足且仍在期限内，只执行原协议准许的首次独立 close。若曾失败或已用，不重试旧入口，不伪补 acceptance，另按原受控新版本流程处理。不得重跑 v30 prepare/launch/run。

候选独立 close 后，才另新版本全量 merge/全部57原序投影/完整 census。仍须全部剩余接触/时间/边未知与可辨识性、完整粗细扩展总体、负控制/反例、所有波及评分报告修正或逐项精确不受影响证明，不能仅重加总旧 counts、忽略 FRONT 或有效报警窗口。不宣称整体修复完成。

## 自动化与防止再次塞满上下文

唯一接续 heartbeat 仍为 automation-2，名称“真实性纠错续研至10月21日24点”，原 created_at1792412413756、间隔8分钟保持。迁移中先 PAUSED，验证新对话成功后再把同一 id 的 target_thread_id 改到新对话并恢复 ACTIVE；不创建第二个 ACTIVE。旧 automation 保持 PAUSED，不操作已删除8/12。

提示只保留本交接文件入口、期限及最小边界。科学进展应写入研究中合规的新版本状态/报告，STATUS.md 只记简短导航、最近证据路径与仍待事项；不要把全部历史复制回提示或回复，不无故修改自动化配置。健康未变化时安静，只有阶段完成、失败、需要人类行动或最终收尾才通知。

到期行政收尾仍按原要求：保存实际新增/未完清单、退出/锁/mutex/签名证据；当前实际 heartbeat 先原生 PAUSED，保存完整配置和停止证据后再 delete；旧 automation 保持 PAUSED。不得自行延长授权。
