"""Freeze a new search core and synthetic outcomes; no real input construction or worker."""
import os
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_unwitnessed_probe_merge_20261022_v1'))
import probe_merge_driver as parent
r=parent.r
SOURCE=ROOT/'src_s4_suffix_witness_search_20261022_v1'
DEV=parent.AUTH/'runtime_sessions/suffix_witness_search_development_tests_v1'


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version used or cutoff')
    h,_=parent.execution()
    with h.exclusive() as mutex:
        _,idle=parent.execution()
        stage=HERE/'suffix_search_staging_v1'; stage.mkdir(exist_ok=False)
        files={'suffix_search_core.py':(HERE/'suffix_search_core_v1.py').read_bytes(),
            'test_suffix_search.py':(HERE/'test_suffix_search_v1.py').read_bytes()}
        for name,blob in files.items(): (stage/name).write_bytes(blob)
        result=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        design={"stage":"pure_synthetic_development_only_not_real_worker",
            "parent_complete_accepted_merge":"resume_20261022_0000_unwitnessed_probe_merge_v1",
            "full_scope_required_later":{"groups":39,"dataset_files":57,"group_unique_points":22857,
                "both_path_scope_records":45714,"point_file_scope_records":26878,"full_original_order_point_file_records":3360000},
            "search":"deterministic bounded midpoint interval priority search of original lower through original horizon",
            "maximum_geometry_queries_per_selected_point":256,"time_resolution_s":1e-7,
            "query_before_original_scientific_lower_forbidden":True,
            "strict_witness_predicate":"body_distance+original_spatial_error+1e-12<=.050000001",
            "pruning_semantics":"strict sufficient witness predicate only; never noncontact, earliest contact or global identifiability",
            "scientific_lower_and_all_original_provenance_unchanged":True,
            "budget_resolution_and_unresolved_frontier_retained_unknown":True,
            "required_before_real_work":["complete scalar independent checker/schema/frontier tests",
                "full current scope driver including all78 paths and114 original-order projections",
                "all parent stopped dependencies/inputs/protocol/signatures/resources admission",
                "final new witness full bracket edge/Decimal70 independent check and original lower-prefix binding",
                "first independent close and new full merge/census"],
            "driver_protocol_prepare_launch_run_close_not_implemented_or_used":True,
            "truth_asset_promotion_allowed":False,"all_expanded_populations_controls_scores_still_required":True}
        r.batch([(DEV/'builder_source.py',Path(__file__).read_bytes()),
            (DEV/'design.json',r.encoded(design)),(DEV/'result.json',r.encoded(dict(time=r.now(),execution=idle,
                mutex=mutex,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,synthetic_only=True)))]
            +[(DEV/name,blob) for name,blob in files.items()])
        print(result.stderr,flush=True)
        r.require(result.returncode==0,'Synthetic failure preserved; no scientific source frozen or real worker')
        r.batch([(SOURCE/name,blob) for name,blob in files.items()])
    print('SUFFIX SEARCH CORE FROZEN AFTER SYNTHETIC TESTS; no real driver/protocol/prepare/run/close',flush=True)


if __name__=='__main__': main()
