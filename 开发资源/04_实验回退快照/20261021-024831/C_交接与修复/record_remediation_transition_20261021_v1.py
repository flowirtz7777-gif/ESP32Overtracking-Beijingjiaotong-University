"""Fresh-scan C-only navigation/config evidence; never modifies frozen research."""
import tomllib
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE

def main():
    admin.prior.parent.configure()
    cfgpath=Path(r'C:\Users\Admin\.codex\automations\automation-2\automation.toml')
    blob=cfgpath.read_bytes(); cfg=tomllib.loads(blob.decode('utf-8-sig'))
    old=tomllib.loads((HERE/'automation-before-result-repair-20261021-v2.toml').read_text(encoding='utf-8-sig'))
    r.require(cfg['status']=='ACTIVE' and cfg['prompt']==admin.prior.PROMPT and cfg['rrule']==old['rrule']
        and cfg['target_thread_id']==old['target_thread_id'] and cfg['created_at']==old['created_at'],'Native config differs')
    status=HERE/'STATUS.md'; prior=status.read_bytes()
    new=r'''# 接续导航（2026-10-21 结果修复转向）

首先遵守HANDOFF.md硬边界；新增人类授权与DeepSeek规则见RESULT_REPAIR_AND_DEEPSEEK_HANDOFF_20261021_v1.md。原STATUS全部无损保存在STATUS.before-result-repair-20261021-v1.md，历史按需读取，禁止全部追加回提示。

## 最近完整接受

v41：ROOT/runs/resume_20261022_0000_edge_cover_merge_v1，worker7312与首次close26368实际wait0、manager41216已退出；AUTH/runtime_sessions/edge_cover_merge_closed_v1/{registration.json,all_closed_run_files_sha256.json}全1119闭合文件重新核签。39组/57原序文件/3360000点—文件记录；当前标签scope26116、组内唯一22226、接触状态未知13949、双路径已有见证边未定12167。全部原lower/upper不变，非完整真值；修正真值评分验收0。报告ROOT/reports/edge_cover_full_merge_close_registration_20261020_v1.md。旧v40在途快照已过时。

## 当前下一阶段（提交不等于准入）

人类已授权开始结果修复。新源ROOT/src_s4_remediation_scope_20261022_v1已冻结，19项纯合成检查通过，v41全部1119闭合文件及原父依赖已重新核签；开发证据AUTH/runtime_sessions/remediation_scope_development_tests_v1/。

首次生命周期待本记录之后提交：C管理器remediation_scope_lifecycle_manager_v1.py，单worker首次prepare/run/close自动顺序wait，失败不重试。新run=runs/resume_20261022_0000_remediation_scope_v1，协议protocol_remediation_scope_20261022_0000_v1.json；新计划v42/v43，实际prepare成功前不称已生成。会话remediation_scope_lifecycle_v1、remediation_scope_launch_v1、remediation_scope_first_close_v1、成功登记remediation_scope_closed_v1。此处不预先声称worker正在运行；每次依实际进程与日志判活，活动CP不读/hash。

本阶段仅完整6609原登记输出文件记录、27条packed扩展总体记录及全部来源/坐标描述文件完整性核验（不是独立实验数）。不读真实数组内容、不重标注/评分/训练，不代表坐标已完整重建或在线预测可直接复用。512MiB新run cap、448MiB预留；原每写RAM计量/fresh全量scandir及所有守卫不变。RAM确定性ZIP保存每一份完整签名源文件并逐字节readback，不再重复写数百独立源文件，原资源计数不变。

原登记ROOT/runs/truth_label_dependency_resolution_20261019_v1/dependency_resolution.json覆盖6609输出/27packed；ROOT/runs/truth_label_impact_registry_20261019_v1/impact_inventory.json覆盖原6498报告，须全部保留。来源元数据close后，推进完整粗细/容差/负控制坐标重建与有效报警/全部评分修复；不能只追基线未知点数量。

## 评分修复关键门

接触时间改变会改变valid与混淆/支持统计，不能固定旧valid；first/raw单值不能代替完整报警序列。区间配对A/B共享同一时间与标签，分子分母联合优化，处理负分子/零分母/EPS；late_A-late_B>0代表B较好。无完整区间几何证据不剪255边集合；现有census不是所有时间阈值不确定性全集。跨零允许反转，中点不当正确标签。先合成反例/小总体穷举独立验证再冻结真实评分版本，形成第一批完整闭环后全范围推广。旧评分/排名/安全推荐暂停，S4整体/M2/S5未完成。仅全部纠错/评分/来源/分组/冻结训练协议准入后允许离线代理训练，最终测试不选参，无实际贝叶斯寻优。

## 定时和 DeepSeek

automation-2已按本次人类指令原生恢复ACTIVE，保留实际15分钟频率、原id/name/created_at/target_thread_id；旧automation保持PAUSED。新prompt见automation-result-repair-prompt-20261021-v1.txt；原/新配置存证automation-before-result-repair-20261021-v2.toml、automation-after-result-repair-20261021-v1.toml。之前8分钟和ACTIVE的旧导航已被实际配置覆盖。

DeepSeek选用现有网页/客户端，本地执行桥、额度触发和唯一控制端交权均未验证；自动接管NOT_ENABLED。交接包已准备，当前所有者仍Codex本线程。额度不足不等于科学进程退出；DeepSeek先只读健康核查，有在途仅监视。没有执行端只能审阅/建议，不伪称已运行。本方恢复先核DeepSeek状态，禁止两个控制端同时推进。详见新交接文件，不以prompt替代原本地守卫。

## 固定边界

截止北京时间2026-10-22 00:00（UTC10月21日16:00），不续期；E只读；E+Z研究目录32GiB，Z预留3GiB；单科学worker/一在途，BLAS单线程。冻结源/协议/输入/结果/失败全保留，旧入口不重跑，活动CP不读/hash；在途不并行真实分析/输入构建/训练，close期间不另开含ROOT监视shell。shell workdir C:\Users\Admin，Python精确路径-X utf8 -B。到期不新科学任务/close，实际退出后仅行政收尾，automation-2原生PAUSED存证后删除，旧automation仍PAUSED。

行政首次尝试因原research runtime禁止写C被拦截（无研究任务使用、无行政文件落盘）；失败源码continue_remediation_20261021_v1.py完整保留。新C-only行政脚本v2每写同样先RAM编码/fresh资源扫描，未改原ROOT-only研究写入守卫；证据result-repair-authority-20261021-v2.json。
'''.encode('utf-8')
    admin.save(HERE/'automation-after-result-repair-20261021-v1.toml',blob)
    admin.save(HERE/'STATUS.before-result-repair-20261021-v1.md',prior)
    r.guard(len(new),0)
    with status.open('wb') as out: out.write(new)
    r.require(status.read_bytes()==new,'Navigation readback differs')
    print('NATIVE AUTOMATION CONFIG AND COMPACT NAVIGATION VERIFIED; ALL PRIOR NAVIGATION PRESERVED',flush=True)

if __name__=='__main__': main()
