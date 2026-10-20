"""New full-current-scope driver, preserving every previous frozen search version."""
import hashlib
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(HERE))
from build_suffix_search_adapter_v2 import replace_function
sys.path.insert(0,str(ROOT/'src_s4_unwitnessed_probe_merge_20261022_v1'))
import probe_merge_driver as current
r=current.r
SOURCE=ROOT/'src_s4_suffix_witness_search_20261022_v3'
DEV=current.AUTH/'runtime_sessions/suffix_witness_search_development_tests_v3'


def driver_source(core_sha):
    text=(ROOT/'src_s4_unwitnessed_probe_20261022_v1/probe_driver.py').read_text(encoding='utf-8')
    text=text.replace('src_s4_local_motion_merge_20261022_v1','src_s4_unwitnessed_probe_merge_20261022_v1')
    text=text.replace('import motion_merge_driver as parent','import probe_merge_driver as parent')
    text=text.replace('import probe_core as core','import search_core as core')
    text=text.replace('resume_20261022_0000_unwitnessed_probe_v1','resume_20261022_0000_suffix_witness_search_v3')
    text=text.replace('protocol_unwitnessed_probe_20261022_0000_v1.json','protocol_suffix_witness_search_20261022_0000_v3.json')
    text=text.replace('resume_plan_20261022_0000_v30.json','resume_plan_20261022_0000_v34.json')
    text=text.replace('resume_plan_20261022_0000_v31.json','resume_plan_20261022_0000_v35.json')
    text=text.replace('runtime_sessions/unwitnessed_probe_launch_v1','runtime_sessions/suffix_witness_search_launch_v3')
    text=text.replace('runtime_sessions/local_motion_merge_closed_v1','runtime_sessions/unwitnessed_probe_merge_closed_v1')
    start=text.index('DEPENDENCIES = '); end=text.index('\nTAGS = ',start)
    text=text[:start]+'''DEPENDENCIES = tuple(dict.fromkeys((PARENT,parent.local.RUN,*parent.DEPENDENCIES,
    CLOSURE,AUTH/"runtime_sessions/unwitnessed_probe_merge_first_close_v1")))'''+text[end:]
    text=text.replace('RESERVATION = 896 * 1024**2','RESERVATION = 3584 * 1024**2')
    text=text.replace('r.RUN, r.RUN_CAP = RUN, 1024**3','r.RUN, r.RUN_CAP = RUN, 4 * 1024**3')
    start=text.index('HASHES = {'); end=text.index('\n\n\ndef configure',start)
    text=text[:start]+'''HASHES = {
    "checkpoint.json":"75a333d219bea885b3e06ac2837af4b3a8f01ad9501eeb34e6cdd56eb9f80a3f",
    "acceptance.json":"e6cff6fe0328720d7efffedd670b25738b12f3b3f203c54d932d3074a14b02fe",
    "close_receipt.json":"7a32aba74f9166bf14685fb334579f593860e922fb295ddd5af37e951658a1ea",
    "source_manifest.json":"a735075b65ab3a93a6bf8638ca43f00d67155e3f1e947c7378f7599d69cff63e"}'''+text[end:]
    gate=r'''
def gate():
    try:
        parent.verify()
        for name,digest in HASHES.items():
            r.require(r.file_hash(PARENT/name)==digest,'Current closed v33 parent dependency changed')
        a=r.read(PARENT/'acceptance.json')
        r.require(a['strict_merged_all_point_prefix_coverage_passed']
            and a['all45714_scope_records_exactly_merged_including_unchanged']
            and a['all_original_scientific_lower_bytes_unchanged']
            and a['accounting']['complete_census_point_file_records']==26878
            and a['accounting']['complete_census_group_unique_points']==22857
            and a['accounting']['combined_status_unknown_point_file_records']==13955
            and a['truth_asset_promotion_allowed'] is False,'Complete accepted current v33 population required')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(PARENT).as_posix():r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.require(actual==inventory and len(actual)==1001,'All1001 stopped closed-parent files required')
        r.require(r.read(AUTH/'runtime_sessions/unwitnessed_probe_merge_first_close_v1/exit.json')['actual_wait_exit_code']==0,
            'Actual parent first-close wait required')
        r.require(r.file_hash(SOURCE/'search_core.py')=='CORE_SHA','Exact synthetic-checked v2 adapter required')
        for name in ('search_core.py','search_control.py','test_search_adapter.py','test_search_control.py'):
            r.require((SOURCE/name).read_bytes()==(ROOT/'src_s4_suffix_witness_search_20261022_v2'/name).read_bytes(),
                'The complete checked v2 kernel/control/tests must be byte-exact reused')
    finally:
        configure()
'''.replace('CORE_SHA',core_sha)
    text=replace_function(text,'gate',gate)
    text=text.replace('unwitnessed_probe_development_tests_v*','suffix_witness_search_development_tests_v*')
    text=text.replace('        AUTH / "runtime_sessions/unwitnessed_probe_development_ready_v1/development_state.json"))',
        '        AUTH / "runtime_sessions/suffix_witness_search_development_tests_v1/design.json"))')
    text=text.replace('    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}',
        '    for folder in ("src_s4_suffix_witness_search_20261022_v1","src_s4_suffix_witness_search_20261022_v2"):\n'
        '        paths.update((ROOT/folder).glob("*.py"))\n'
        '    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}',1)
    text=replace_function(text,'path_iter',r'''
def path_iter(key,loaded,groups,asset):
    return parent.local.path_iter(key,loaded,groups,asset)
''')
    text=text.replace('("merge_", "upper_merge_", "local_motion_")','("merge_", "upper_merge_", "local_motion_", "probe_merge_")')
    text=replace_function(text,'whole_counts',r'''
def whole_counts(value):
    r.require(value['path_blocks']==78 and value['projected_path_files']==114
        and value['scope_group_unique_points']==22857 and value['scope_point_file_records']==26878
        and value['group_point_path_records_not_independent_samples']==45714
        and value['group_path_totals']['selected_unwitnessed']==22834
        and value['group_path_totals']['scientific_lower_changes']==0,'Complete current both-path scope required')
    for tag,selected,edge in (('oldpath',13955,12923),('independent',13707,12645)):
        row=value['weighted_path_diagnostics'][tag]
        r.require(row['selected_unwitnessed']==selected
            and row['source_initial_unknown']+row['source_time_leaf_unknown']==selected
            and row['source_witnessed_edge_unknown_exact_reuse']==edge,
            'Every remaining original initial/leaf unknown and existing witnessed-edge unknown required')
''')
    text=text.replace('20261022-0000-v30','20261022-0000-v34').replace('20261022-0000-v31','20261022-0000-v35')
    text=text.replace('full-current-scope-supplemental-unwitnessed-witness-candidates-v1','full-current-scope-bounded-suffix-witness-candidates-v3')
    text=text.replace('"original lower, then min(horizon,lower+1e-7*2**j), up to64"',
        '"original lower; deterministic full-suffix midpoint priority splits, every original interval motion bound, max256 queries"')
    text=text.replace('UNWITNESSED PROBE','SUFFIX WITNESS SEARCH')
    text=text.replace('unwitnessed_probe_candidates_20261022_0000_v1.md','suffix_witness_search_candidates_20261022_0000_v3.md')
    text=text.replace('unwitnessed-probe-candidates','suffix-witness-candidates')
    text=text.replace('unwitnessed-probe-running','suffix-witness-search-running')
    text=text.replace('supplemental strict witness candidates','bounded suffix strict witness candidates')
    text=text.replace('Every scalar probe GEOS/full bracket Decimal70/finite face/field/projection/padding checked.',
        'Every successful and failed scalar probe GEOS, exact budget/control/frontier replay, full bracket Decimal70, finite face, field/projection/padding checked.')
    text=text.replace('"independent_close": "all scalar probes GEOS/strict final witnesses/full brackets Decimal70/finite faces/all arrays and original-order projections"',
        '"independent_close": "all scalar GEOS probes; exact split/priority/budget/frontier replay; strict final witnesses/full brackets Decimal70/finite faces/all arrays and original-order projections"')
    compile(text,'suffix_driver.py','exec')
    return text.encode('utf-8')


def driver_tests():
    text=(ROOT/'src_s4_unwitnessed_probe_20261022_v1/test_probe_driver.py').read_text(encoding='utf-8')
    text=text[:text.index('    def counts(self):')]
    text=text.replace('import probe_driver as d','import suffix_driver as d')
    text=text.replace('("merge_", "upper_merge_", "local_motion_")','("merge_", "upper_merge_", "local_motion_", "probe_merge_")')
    text=text.replace('("local_motion", ("selected", "certified", "changed"))',
        '("local_motion", ("selected", "certified", "changed")),\n'
        '                              ("probe_merge", ("scope", "new_witness", "changed"))')
    for old,new in (('(6, 64)','(6, 256)'),('(0, 64)','(0, 256)'),('(3, 64)','(3, 256)')):
        text=text.replace(old,new)
    text=text.replace('self.assertEqual(out[name].shape, (4, 64))',
        'width=256 if prefix=="forward" else 64\n            self.assertEqual(out[name].shape, (4, width))')
    text=text.replace('self.assertEqual(packed.shape, (32,))','self.assertEqual(packed.shape, (4*width//8,))')
    text+='\nif __name__=="__main__": unittest.main()\n'
    compile(text,'test_suffix_driver.py','exec')
    return text.encode('utf-8')


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version used or cutoff')
    h,_=current.execution()
    with h.exclusive() as mutex:
        _,idle=current.execution()
        previous=ROOT/'src_s4_suffix_witness_search_20261022_v2'
        files={p.name:p.read_bytes() for p in previous.glob('*.py')}
        files['suffix_driver.py']=driver_source(hashlib.sha256(files['search_core.py']).hexdigest())
        files['test_suffix_driver.py']=driver_tests()
        stage=HERE/'suffix_search_staging_v3'; stage.mkdir(exist_ok=False)
        for name,blob in files.items(): (stage/name).write_bytes(blob)
        # Stage driver root resolution is redirected only in the synthetic stage copy, not in frozen source.
        staged_driver=files['suffix_driver.py'].decode('utf-8').replace('ROOT = Path(__file__).resolve().parents[1]',
            'ROOT = Path(r"Z:\\大创内轮差项目_实验结果\\科研实验_2026-10-14")')
        (stage/'suffix_driver.py').write_text(staged_driver,encoding='utf-8')
        results=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        r.batch([(DEV/'builder_source.py',Path(__file__).read_bytes()),
            (DEV/'synthetic_driver_stage_only.py',staged_driver.encode('utf-8')),
            (DEV/'result.json',r.encoded(dict(time=r.now(),returncode=results.returncode,stdout=results.stdout,
                stderr=results.stderr,execution=idle,mutex=mutex,pure_synthetic_only=True,
                synthetic_stage_root_resolution_only_redirected=True,frozen_driver_source_not_redirected=True,
                core_control_and_prior30tests_byte_exact=True)))]
            +[(DEV/name,blob) for name,blob in files.items()])
        print(results.stderr,flush=True)
        r.require(results.returncode==0,'Synthetic failure preserved; no real prepare/run')
        r.batch([(SOURCE/name,blob) for name,blob in files.items()])
    print('COMPLETE V3 DRIVER FROZEN AFTER ALL SYNTHETIC TESTS; REAL PREPARE/RUN STILL UNUSED',flush=True)


if __name__=='__main__': main()
