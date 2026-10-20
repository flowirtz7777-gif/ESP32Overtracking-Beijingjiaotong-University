"""Second preserved development test version; pure merge core and driver unchanged."""
import os
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import build_probe_merge_v1 as first
r,probe,ROOT=first.r,first.probe,first.ROOT
SOURCE=first.SOURCE
DEV=probe.AUTH/'runtime_sessions/unwitnessed_probe_merge_development_tests_v2'


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version used or cutoff')
    h,_=probe.execution()
    with h.exclusive() as mutex:
        _,idle=probe.execution()
        core=(HERE/'probe_merge_core_v1.py').read_bytes()
        oldtests=(HERE/'test_probe_merge_v1.py').read_text(encoding='utf-8')
        old="args[2][field][0] = 1"
        new="args[2][field][0] = (not args[2][field][0]) if args[2][field].dtype == np.bool_ else args[2][field][0] + 1"
        r.require(oldtests.count(old)==1,'Original test binding differs')
        tests=oldtests.replace(old,new).encode('utf-8')
        driver=first.build_driver().encode('utf-8')
        prior=first.DEV
        r.require((prior/'probe_merge_core.py').read_bytes()==core
            and (prior/'probe_merge_driver.py').read_bytes()==driver,'Do not change scientific core or driver for test fix')
        stage=HERE/'probe_merge_staging_tests_v2'
        stage.mkdir(exist_ok=False)
        for name,blob in (('probe_merge_core.py',core),('test_probe_merge.py',tests),('probe_merge_driver.py',driver)):
            (stage/name).write_bytes(blob)
        result=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        evidence=dict(time=r.now(),execution=idle,mutex=mutex,returncode=result.returncode,
            stdout=result.stdout,stderr=result.stderr,pure_synthetic_only=True,
            original_failure_preserved=str(prior),pure_core_and_driver_byte_exact_with_first_development_version=True,
            test_fix='Boolean immutable-field mutation now actually flips the value; no science changes')
        r.batch([(DEV/'development_test.json',r.encoded(evidence)),(DEV/'builder_source.py',Path(__file__).read_bytes())]
            +[(DEV/name,blob) for name,blob in (('probe_merge_core.py',core),('test_probe_merge.py',tests),('probe_merge_driver.py',driver))])
        print(result.stderr,flush=True)
        r.require(result.returncode==0,'Development tests failed; source not frozen/admitted')
        r.batch([(SOURCE/name,blob) for name,blob in (('probe_merge_core.py',core),('test_probe_merge.py',tests),('probe_merge_driver.py',driver))])
    print('ALL20 SYNTHETIC TESTS PASS; NEW SOURCE FROZEN; prepare/run not yet used',flush=True)


if __name__=='__main__': main()
