"""Record synthetic repairs and a human-pastable native-client handoff. No science."""
import hashlib
import io
import json
import sys
import tomllib
import unittest
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE

DOC=r'''# ZCode 原客户端执行交接 v2：修复准入、证据和顺序问题

## 使用方式与授权
只由人类粘贴本次消息到既有ZCode会话sess_d355bd21-3bd6-4884-a0e0-0f66ac854cfe后，从原客户端执行；不再经外部headless CLI派发，不重开会话，不换模型/provider，不切yolo或改权限绕过审批。Codex科研和automation-2继续PAUSED，本文件不恢复它们。

旧CLI控制器已于北京时间02:03:03结束8轮，未满原01:48—02:48窗口，所有日志和失败保留，弃用不再启动。旧control/试运行脚本不改写、不重新计时。只有人类实际粘贴发送“在客户端开始新的一小时”才授权本次客户端新窗口；P0实测通过后，通过下述一次性入口保存start/end=min(start+1h,原总截止)。没有这条人类客户端指令就不创建新窗口；原总截止仍北京时间2026-10-22 00:00，不续期。新窗口文件存在后禁止自动重置或延长。到点禁新科学任务/close，已提交块自然退出保存断点，不强杀/清锁，不自动恢复Codex。

## 五项已修复的问题——原错误结论一律撤回

1. 缺全系统精确argv、完整锁、原mutex取得释放或追加日志证据，P0必须NOT_ADMITTED。不能用MSYS /proc、旧PID、零写入或旧快照替代，不能同时写“缺证据”和“P0完成”。此前DeepSeek据替代证据宣布无在途不获接受。
2. 找到文件/来源链、file SHA和数量算术一致，只能记source_link_identified。18条未解记录没有实际重建全数组并验array SHA/原序/分组/容差，仍不能称P1闭合。v43的9/18是描述链接状态，不等于坐标是否物理存在，也不因文字发现被改写。P1必须另新冻结版本完整重建并独立close；不得推迟到P3以后。
3. “trace与评分器完全语义等价”已被合成反例推翻。time=[2]、hit=True、contact=NaN时，旧trace输出FP=0/negative_opportunities=0，评分语义应为1/1。time=[2]、contact=3、front_ignored=True时旧trace输出TP=1，评分器应为0。完整证据见client-handoff-repairs-evidence-20261021-v2.json；不要再逐行读码就宣布等价。
4. 仅源码确认可复用confirmation逻辑，不等于现存磁盘有完整确认报警序列，也不等于已复现新真值评分。需要同输入/配置/目标坐标/几何/逐帧horizon/确认状态的实际重放和独立数值对照。first/raw/valid单值不能代替完整序列。
5. 第一次出现No permission client configured即停止实际推进并报告。tool_error_count=0或CLI进程exit0都不能抹去工具结果中的权限拒绝。不要多轮重复探测，不改权限模式绕过。本地客户端正常审批通道解决后再按实际状态续接，旧科学入口仍禁重跑。

## P0 可直接使用的只读检查程序
`client_readonly_admission_check_v3.py` 位于本文件同目录。必须由原客户端以精确Python、workdir C:\Users\Admin运行：

    C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8 -B C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1\client_readonly_admission_check_v3.py --origin zcode-client --start-client-hour

工具有workdir参数时显式设C:\Users\Admin；若仅Git Bash command，第一条cd /c/Users/Admin，使用同一精确python.exe，不能调用bare python。程序只读ROOT的状态、注册日志和锁，不读/hash任何CP，不调用科学prepare/run/close；通过原冻结执行守卫、真实全系统CIM、原mutex取得释放和fresh完整资源扫描，向C写行政证据。它核实实际进程祖先含ZCode.exe；Codex自测不冒充客户端通过。

只有同时取得：状态P0_SNAPSHOT_COMPLETE_PENDING_ACTUAL_TOOL_EXIT0、native_zcode_ancestry_observed=true、原客户端工具真实exit0、完整快照/源SHA/正常mutex释放、无在途/未知冲突、PAUSED配置，才完成本次P0。程序正常退出但status=NOT_ADMITTED仍未准入；程序内部不能预先伪造自身wait0。快照通过只代表当次健康，真实阶段入口仍须重新原守卫核验。

原生客户端新窗口一次性记录在client-execution-window-20261021-v2.json；只有人类本次粘贴明确启动新小时才使用--start-client-hour。已有文件只复核、不重置。每次新任务/close检查窗口和实时时钟，完整冻结新协议绑定min(新窗口截止,原总截止)及块级停止；不改冻结旧runtime。

## 严格继续 Codex 原计划

P1-real：以v43闭合来源为父依赖，覆盖全部6609输出文件记录、27packed扩展总体及57基线/完整粗细/不同容差/负控制/反例的来源。按原生成器重建完整坐标原序，逐项核实file+array SHA、dtype/shape/group/容差/前缀+delta，保留旧标签legacy未认证。source_link_identified、输入已重建、候选、独立闭合分别记录。用client_execution_contract_v2.py检查状态契约，但JSON字段不能替代真正签名/验收；新冻结source/protocol、首次prepare/run和独立close全部依原协议。编号v44/v45仅原候选，先核是否已用。

P2-real：必须等P1实际独立闭合；P1在途时只允许不读真实数据的代码/协议/合成准备，不能借此跳过P1。接入下述候选核心，并新冻结完整报警序列重建/必要重放版本，保存逐帧真实horizon、确认状态、causal输入；不使用未来真值参与在线预测，不重跑旧run。

P3-real：P0和P1及评分/序列输入依赖真实准入后，才对预先按原登记顺序固定的首批完整总体执行真实评分及独立close。DeepSeek先前提到“8条件现成”只是候选线索，未经冻结试点清单和原序依赖验证不能自动视为正式试点。现有26116 census不是所有时间阈值不确定性全集，不能把范围外旧标签全部当正确。

P4：交付源/协议/输入输出签名、实际命令及真实wait、资源快照、测试、完整验收/receipt或单项精确不受影响证明、未完/冲突/失败清单。只完成子项就只报告子项；旧标签评分/排名/安全推荐不恢复，真实纠错评分认证仍0直到真实通过。窗口结束做行政交接，无自动Codex恢复。

## 已准备的新候选代码（均未科学冻结或真实评分认证）
- paired_interval_metric_core_v2.py：显式指定valid_alarm_start（scored取2，legacy才可显式None），A/B共享时间/标签/分母，分子分母联合比值，保留零分母。原uint8 possible_edge_codes=255是位掩码，decode_edge_mask得到1..8，禁止当一个原子面或无证剪为{1,2,5}；迭代器只物化一次，避免分割后报警流耗尽。分数理性算术模型不能直接声称与浮点评分器逐bit等价，真实适配须数值包络或独立边界验证。
- scored_trace_adapter_core_v1.py：保留评分前确认历史热启动，但first/valid按真实评分起点门控；接触时间变化后重构valid；补齐负例FP/opportunities及非eligible正例筛选，区分真实逐帧horizon与共同2s参考。候选合同仅horizon>=2；低于2的策略拒绝，不能默认覆盖。该dense函数只用于小合成检查，真实大总体必须另新流式/分块受控实现，不能直接临时脚本跑真实数据。
- client_execution_contract_v2.py：缺完整P0证据即拒绝；P1缺全数组独立闭合不准P2-real/P3-real；首次权限拒绝即停；按真实时限而非固定8轮结束；只读/合成准备不冒充真实阶段完成。它是状态契约检查，不是自动证据生成器或OS安全沙箱。
- test_client_execution_repairs_v2.py、test_paired_interval_metric_core_v2.py与原v1回归：共33项合成检查通过（原13+新增20），包括原冻结trace负例/资格筛选反例、100组独立逐点逐帧标量评分对照、300组配对比值穷举。只验证候选代码，不等于数据/实验/完整评分验收。

## 固定硬边界（不因换客户端改变）
E全部只读；ROOT=Z:\大创内轮差项目_实验结果\科研实验_2026-10-14；E+Z研究目录32GiB，Z物理预留3GiB；单科学worker/一在途，BLAS单线程。每次研究写前RAM编码计量+原runtime fresh全量scandir；原守卫不改不绕。冻结源/协议/输入/结果/失败不删改搬移，已用入口不重跑；未知/冲突/预算不足不当负例；原阈值/误差/角点/可靠性门不放宽。shell workdir C:\Users\Admin，精确Python-X utf8 -B，禁止临时python -c真实分析。C只放代码/合成/行政，不能复制真实数组绕预算；旧DeepSeek在E的MD/PY原样保留且计入预算。

有在途仅监视真实计算，活动CP不读/hash，不并行真实数据分析/输入/训练；close期间不另开含ROOT监视shell。旧RIGHT/FRONT/接触时间/漏报/混淆/排名/84配置/部署推荐暂停；S4整体/M2/S5未完成，M2/S5不准入。只有纠错、全部受影响评分、来源、整轨迹及同源分组、冻结训练协议全部准入才允许离线代理训练；最终测试不选参，无实际贝叶斯寻优/部署授权。

原完整边界见HANDOFF.md、RESULT_REPAIR_AND_DEEPSEEK_HANDOFF_20261021_v1.md；执行路线见DEEPSEEK_ORIGINAL_PLAN_TRIAL_20261021_v1.md。本文件仅纠正已证实错误和客户端发起方式；不放宽原研究约束。STATUS.md旧在途/ACTIVE快照以最新记录覆盖。不要全量历史塞回上下文。
'''

PASTE=r'''请在这个既有ZCode会话中，作为执行者继续Codex已经确定的计划，严格按下面文件推进，不重新设计研究路线：
C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1\CLIENT_EXECUTION_HANDOFF_20261021_v2.md

这是我从原客户端发起的新一次一小时试运行授权：先完成文件规定的真实P0核验；P0通过并取得工具真实exit0后，以新窗口文件记录的时刻开始一小时，不超过原总截止北京时间2026-10-22 00:00。旧CLI控制器和窗口不要重启、重置或延长；已有本次新窗口则不得重复开始。Codex科研定时任务保持PAUSED，不与它并行提交任务。

先读取上述文件、最新STATUS.md，以及client-handoff-repairs-evidence-20261021-v2.json。通过客户端正常权限通道运行client_readonly_admission_check_v3.py --origin zcode-client --start-client-hour；所有shell workdir=C:\Users\Admin，Python必须精确原路径-X utf8 -B。若权限拒绝或缺进程/mutex证据，第一次就停并报告，不能换成零写入、旧PID或MSYS /proc后宣布通过，也不要改yolo或绕过审批。

P0→P1完整坐标/来源链的全数组新冻结与独立闭合→P2接入修正评分核心和完整报警序列→P3首批真实评分独立验收→P4交付；禁止把P1推迟到推广阶段。复用新候选paired_interval_metric_core_v2.py、scored_trace_adapter_core_v1.py及client_execution_contract_v2.py，先核来源和33项合成证据，再走完整真实准入。旧trace“完全等价”的判断已被负例误报和资格筛选两个反例推翻，不能沿用。

E只读、32GiB/3GiB、单worker/一在途、逐写RAM计量+fresh全量scandir、冻结资产和失败全保留、旧入口禁重跑、活动CP不读/hash、科学阈值和训练门全部保持。不要只写建议或重复宣告准备完成；必须交付实际代码、测试、源/输入输出签名、真实退出码与独立验收，或清楚的单项阻塞。到点停止新任务和close，已提交块自然退出后交接，不自动恢复Codex。
'''

def main():
    stream=io.StringIO(); suite=unittest.TestSuite()
    for module in ('test_paired_interval_metric_core_v1','test_client_execution_repairs_v2','test_paired_interval_metric_core_v2'):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    names=('paired_interval_metric_core_v1.py','paired_interval_metric_core_v2.py','scored_trace_adapter_core_v1.py',
        'client_execution_contract_v2.py','client_readonly_admission_check_v2.py','client_readonly_admission_check_v3.py',
        'test_paired_interval_metric_core_v1.py','test_client_execution_repairs_v2.py','test_paired_interval_metric_core_v2.py')
    cfgpath=Path(r'C:\Users\Admin\.codex\automations\automation-2\automation.toml')
    cfg=tomllib.loads(cfgpath.read_text(encoding='utf-8-sig'))
    if cfg['status']!='PAUSED': raise RuntimeError('Codex scheduler unexpectedly resumed')
    files={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names}
    original={str(p):r.file_hash(p) for p in (
        r.ROOT/'src_s4_temporal_trace_v2/run_trace.py',r.ROOT/'src_s4_v1/evaluation_scored.py',
        r.ROOT/'src_s4_edge_interval_cover_20261022_v2/edge_cover_core.py')}
    evidence=dict(time=r.now(),tests_run=result.testsRun,successful=result.wasSuccessful(),failures=len(result.failures),
        errors=len(result.errors),test_transcript=stream.getvalue(),candidate_source_sha256=files,
        original_frozen_source_sha256=original,original_frozen_files_modified=False,
        pure_synthetic_inputs_only=True,real_coordinate_arrays_reconstructed=False,
        real_scoring_or_independent_scientific_acceptance=False,scientific_workers_started=0,
        native_client_permission_gate_not_yet_passed=True,codex_precheck_did_not_claim_native_client_admission=True,
        original_trace_negative_false_alarm_actual=0,corrected_synthetic_negative_false_alarm=1,
        original_trace_ineligible_front_TP_actual=1,corrected_synthetic_ineligible_front_TP=0,
        codex_automation_status=cfg['status'],old_cli_controller_retired=True,
        no_client_hour_started_by_codex=True)
    admin.save(HERE/'client-handoff-repairs-evidence-20261021-v2.json',r.encoded(evidence))
    if not result.wasSuccessful() or result.testsRun!=33: raise RuntimeError('Preserved tests failed; no completion claim')
    admin.save(HERE/'CLIENT_EXECUTION_HANDOFF_20261021_v2.md',DOC.encode('utf-8'))
    admin.save(HERE/'粘贴给DeepSeek_客户端执行_v2.txt',PASTE.encode('utf-8'))
    status=HERE/'STATUS.md'
    update=('\n\n## 最新：弃用外部CLI，等待人类从原客户端粘贴执行（'+r.now()+'）\n\n'
        '人类要求手动粘贴到ZCode客户端，由Codex先修复执行缺陷。automation-2仍PAUSED，Codex不提交科研。'
        '旧CLI控制器于北京时间02:03:03在8轮后结束，因No permission client configured只做了只读查证，'
        '没有完成一小时，也没有新代码/真实输入构建/评分/独立close。CLI退出0与tool_error_count0不等于权限或科研成功；'
        '完整失败/日志保留，不再启动旧控制器。DeepSeek此前“P0完成”缺全系统argv和mutex证据，不接受；'
        '18未解坐标仅有路径/部分file SHA线索，不等于P1已实际重建闭合。\n\n'
        '新交接CLIENT_EXECUTION_HANDOFF_20261021_v2.md，可粘贴文本“粘贴给DeepSeek_客户端执行_v2.txt”。'
        '仅人类实际从原客户端发送新的明确一小时指令后，才可通过client_readonly_admission_check_v3.py '
        '--origin zcode-client --start-client-hour创建一次性client-execution-window-20261021-v2.json；'
        'Codex未开始新窗口，旧窗口不重置，不越过原总截止。原客户端系统审批，禁止切yolo/改守卫绕过。'
        'Codex自身只读预检已正常exit0，但正确返回P0_NOT_ADMITTED/native_zcode_ancestry=false，未冒充客户端准入；'
        '快照client-p0-snapshot-20261020T183959352244Z.json。\n\n'
        '实质代码修复：scored_trace_adapter_core_v1.py补无接触负例FP/opportunities和非eligible正例筛选，'
        '保留pre-score确认热启动、scored first/valid门和逐帧horizon/共同2s参考。'
        '原冻结trace已用纯合成反例证伪“完全等价”：negative FP0应1、front ignored TP1应0。'
        'paired_interval_metric_core_v2.py显式valid起点、拒绝255作为原子面（它是1..8位掩码）、物化迭代器避免耗尽、'
        '验证paired base；理性算术不是浮点bit级证明。client_execution_contract_v2.py拒绝缺P0/缺P1实数组闭合而推进真实P2/P3，'
        '首次权限拒绝就停，不按固定8轮提前停。共33纯合成测试通过，含300配对穷举+100独立标量逐帧对照；'
        '证据client-handoff-repairs-evidence-20261021-v2.json。均C候选，未冻结Z科学源、未真实重建/评分/训练，'
        '真实评分验收仍0；E/Z冻结代码和所有失败均未改删移。\n').encode('utf-8')
    blob=status.read_bytes()+update; r.guard(len(blob),0)
    with status.open('wb') as out: out.write(blob)
    print(stream.getvalue(),flush=True)
    print('CLIENT HANDOFF REPAIRS PACKAGED;33 SYNTHETIC TESTS PASSED; SCIENTIFIC SCHEDULER STAYS PAUSED',flush=True)

if __name__=='__main__': main()
