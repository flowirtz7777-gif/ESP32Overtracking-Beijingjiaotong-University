"""C-only navigation and synthetic evidence while scientific worker is active."""
import hashlib
import subprocess
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE

def main():
    # No execution(), research CP read/hash, real array read, or research write.
    test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(HERE),
        '-p','test_paired_interval_metric_core_v1.py','-v'],cwd=r'C:\Users\Admin',
        capture_output=True,encoding='utf-8',timeout=60)
    blobs={name:(HERE/name).read_bytes() for name in ('paired_interval_metric_core_v1.py','test_paired_interval_metric_core_v1.py')}
    evidence=dict(time=r.now(),returncode=test.returncode,stdout=test.stdout,stderr=test.stderr,
        source_sha256={name:hashlib.sha256(blob).hexdigest() for name,blob in blobs.items()},
        data_scope='pure synthetic only; 13 tests including300 full Cartesian small-population comparisons',
        metric_scope='paired RIGHT insufficient percentage only; not all confusion/FP/quantile metrics',
        frozen_scientific_source=False,real_data_adapter_implemented=False,real_prediction_reuse_accepted=False,
        real_scores_accepted=False,scientific_worker_inflight_not_touched=True)
    admin.save(HERE/'paired-metric-candidate-synthetic-checks-20261021-v1.json',r.encoded(evidence))
    r.require(test.returncode==0,'Synthetic candidate failed; preserve outcome')
    addition=('\n\n## 实际启动更新（'+r.now()+'）\n\n'
        'remediation_scope_lifecycle_manager_v1.py已实际提交，工具exec session45064；行政manager28320，'
        '首次prepare28432实际wait退出0，唯一科学worker47228精确argv为scope_driver.py run，'
        '实时通用CIM已核对。prepare/run入口均已用，禁止重跑。管理器追加日志最近采样已见DONE FULL REMEDIATION SCOPE4352/6609；'
        '这只是已见进度下界，不代表完整准入/验收；尚未观察首次close。优先write_stdin轮询session45064，'
        '不读/hash活动CP，不另开含ROOT的监视shell。完整接受基线仍v41；新v42已由prepare生成、v43尚未接受。\n\n'
        '在途只做C盘纯合成准备：paired_interval_metric_core_v1.py与test_paired_interval_metric_core_v1.py，'
        '13项检查通过（含300组小总体完整笛卡尔穷举），完整证据paired-metric-candidate-synthetic-checks-20261021-v1.json。'
        '候选重构随contact变化的valid，A/B共享时间、分母与标签，用边界单点/开区间代表覆盖分段状态，'
        '按可选点贡献斜率前缀求分子分母联合分式极值，保留零分母并禁止据此严格排名。'
        '仅RIGHT insufficient配对百分比候选，不覆盖混淆/误报/提前量分位数；未冻结科学源、无真实适配器、'
        '无真实标签/评分认证。跨点独立domain只是几何约束的放松，界不等于可达性或真值；'
        '需完整报警序列和已认证的真值域superset，禁止固定旧valid。下一阶段须补真实协议/完整来源/独立验收。\n').encode('utf-8')
    status=HERE/'STATUS.md'; payload=status.read_bytes()+addition
    r.guard(len(payload),0)
    with status.open('wb') as target: target.write(payload)
    r.require(status.read_bytes()==payload,'C navigation readback differs')
    print('C NAVIGATION AND SYNTHETIC13-TEST CANDIDATE EVIDENCE SAVED; ACTIVE CP UNTOUCHED',flush=True)

if __name__=='__main__': main()
