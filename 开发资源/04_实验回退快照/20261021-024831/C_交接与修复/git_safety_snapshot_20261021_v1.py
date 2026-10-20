"""User-authorized remote rollback checkpoint; alternate index, no worktree writes.

Exclude research data/run trees and active CPs. Preserve current branch/index;
add byte-exact C/Z source snapshots virtually to the backup commit only.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE
REPO=Path(r'E:\大创内轮差项目')
ZROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
PREFIXES=('工具/转弯全过程盲区分析软件/科研实验_2026-10-14/',
          '工具/转弯全过程盲区分析软件/自动化批量实验/')
CODE_EXT={'.py','.m','.js','.c','.cpp','.h','.hpp','.md','.json'}
SENSITIVE_NAMES={'credentials.json','provider_config.json','id_rsa','id_ed25519','.env','.npmrc','.pypirc'}
PATTERNS=(('private_key',re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('github_token',re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})')),
    ('api_key_token',re.compile(rb'\bsk-[A-Za-z0-9_-]{28,}\b')))

def git(args,*,env=None,data=None):
    done=subprocess.run(['git','-C',str(REPO),*args],cwd=r'C:\Users\Admin',env=env,
        input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if done.returncode: raise RuntimeError('git '+args[0]+' failed: '+done.stderr.decode('utf-8',errors='replace')[-2500:])
    return done.stdout

def forbidden(name): return any(name.startswith(p) for p in PREFIXES)

def csave(path,blob):
    r.guard(len(blob),0)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as out: out.write(blob)
    if path.read_bytes()!=blob: raise RuntimeError('C checkpoint evidence readback differs')

def inspect_blob(name,blob):
    if Path(name).name.lower() in SENSITIVE_NAMES: raise RuntimeError('Sensitive filename excluded: '+name)
    if len(blob)>50*1024**2: raise RuntimeError('File exceeds project50MiB policy: '+name)
    for label,pattern in PATTERNS:
        if pattern.search(blob): raise RuntimeError('Potential '+label+' in '+name+'; value not printed')

def main():
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))); stamp=now.strftime('%Y%m%d-%H%M%S')
    outdir=HERE/('git_safety_'+stamp)
    branch='codex/safety-before-deepseek-'+stamp
    ref='refs/heads/'+branch
    alt=outdir/'index'
    env={**os.environ,'GIT_INDEX_FILE':str(alt)}
    base=git(['rev-parse','HEAD']).decode().strip()
    current_branch=git(['symbolic-ref','--short','HEAD']).decode().strip()
    gitdir=Path(git(['rev-parse','--absolute-git-dir']).decode().strip())
    real_index=gitdir/'index'; original_index_sha=hashlib.sha256(real_index.read_bytes()).hexdigest() if real_index.exists() else None
    tracked=[v.decode('utf-8') for v in git(['ls-files','-z']).split(b'\0') if v]
    untracked=[v.decode('utf-8') for v in git(['ls-files','--others','--exclude-standard','-z']).split(b'\0') if v]
    selected=sorted({p for p in tracked+untracked if not forbidden(p)})
    original={}; count=0; total=0
    for name in selected:
        path=REPO/name
        if not path.exists(): continue
        if not path.is_file() or path.is_symlink(): raise RuntimeError('Explicit file review required: '+name)
        blob=path.read_bytes(); inspect_blob(name,blob)
        original[str(path)]=hashlib.sha256(blob).hexdigest(); count+=1; total+=len(blob)
    # Backup current source/control state only; never iterate or hash a run CP.
    external={}
    for folder in ZROOT.iterdir():
        if folder.is_dir() and folder.name.startswith('src'):
            for path in folder.rglob('*'):
                if path.is_file() and path.suffix.lower() in CODE_EXT and not path.is_symlink():
                    external['Z_研究源码/'+path.relative_to(ZROOT).as_posix()]=path
    for path in ZROOT.iterdir():
        if path.is_file() and (path.name.startswith(('protocol','resume_plan','research_validity_overlay')) or path.name=='active_research_run.json'):
            external['Z_控制协议/'+path.name]=path
    for path in HERE.iterdir():
        if path.is_file() and (path.suffix=='.py' or path.name in (
            'HANDOFF.md','STATUS.md','CLIENT_EXECUTION_HANDOFF_20261021_v2.md',
            'DEEPSEEK_ORIGINAL_PLAN_TRIAL_20261021_v1.md','RESULT_REPAIR_AND_DEEPSEEK_HANDOFF_20261021_v1.md',
            '原自动化实验规划核对_20261020.md','今晚加速与训练准入草案_20261020.md',
            '粘贴给DeepSeek_客户端执行_v2.txt','client-handoff-repairs-evidence-20261021-v2.json',
            'paired-metric-candidate-synthetic-checks-20261021-v1.json')):
            external['C_交接与修复/'+path.name]=path
    # Preserve original E research source/notes without adding its data trees.
    for relroot,label in ((PREFIXES[0].rstrip('/'),'E_旧科研源码'),(PREFIXES[1].rstrip('/'),'E_旧批量源码')):
        folder=REPO/relroot
        for path in folder.iterdir():
            if path.is_file() and path.suffix.lower() in CODE_EXT and not any(t in path.name.lower() for t in ('checkpoint','lock','credential')):
                external[label+'/'+path.name]=path
            elif path.is_dir() and path.name.startswith(('src','scripts')):
                for child in path.rglob('*'):
                    if child.is_file() and child.suffix.lower() in CODE_EXT and not child.is_symlink():
                        external[label+'/'+child.relative_to(folder).as_posix()]=child
    virtual={}; source_info={}
    backup_root='开发资源/04_实验回退快照/'+stamp
    for rel,path in sorted(external.items()):
        blob=path.read_bytes(); inspect_blob(str(path),blob)
        sha=hashlib.sha256(blob).hexdigest(); original[str(path)]=sha
        virtual[backup_root+'/'+rel]=blob
        source_info[rel]=dict(original_path=str(path),bytes=len(blob),sha256=sha)
    manifest=dict(created_beijing=now.isoformat(timespec='seconds'),branch=branch,base_commit=base,
        original_working_branch=current_branch,repository_files_existing=count,repository_file_bytes=total,
        external_source_files=len(virtual),external_source_bytes=sum(map(len,virtual.values())),
        excluded_untracked_research_records=sum(forbidden(p) for p in untracked),
        original_index_sha256=original_index_sha,excluded_bulk_directories=PREFIXES,
        active_checkpoints_not_read_or_hashed=True,large_research_results_not_backed_up_in_git=True,
        no_project_worktree_or_real_index_or_frozen_research_file_modified=True,
        source_snapshots=source_info)
    virtual[backup_root+'/snapshot_manifest.json']=r.encoded(manifest)
    readme=('# DeepSeek接管前回退快照\n\n'
        '本分支保存创建时项目工作区的代码/文档/目录重组，以及C交接修复脚本、E/Z研究源码和控制协议的逐字节快照。'
        '原工作分支及真实暂存区保持不变；快照目录仅出现在此备份提交中。\n\n'
        '大型实验数据、运行结果、活动checkpoint及凭据不在本Git备份范围。冻结研究资料仍按原协议保留，'
        '源码备份不代表实验已修复/验收。恢复研究源码应先提取到新目录并核manifest，不能直接覆盖冻结历史。'
        '不要用git clean或reset --hard清理现有研究资料。\n').encode('utf-8')
    virtual[backup_root+'/README.md']=readme
    csave(outdir/'snapshot_manifest.json',r.encoded(manifest))
    csave(outdir/'selected_project_paths.nul',b'\0'.join(p.encode('utf-8') for p in selected)+b'\0')
    r.guard(1024**2,0)
    git(['read-tree',base],env=env)
    git(['add','-A','--pathspec-from-file='+str(outdir/'selected_project_paths.nul'),'--pathspec-file-nul'],env=env)
    # Ensure source Git objects already present under excluded paths cannot enter.
    staged=[v.decode('utf-8') for v in git(['ls-files','-z'],env=env).split(b'\0') if v]
    if any(forbidden(p) for p in staged): raise RuntimeError('Research data prefix unexpectedly staged')
    index_lines=[]
    for name,blob in sorted(virtual.items()):
        oid=git(['hash-object','-w','--stdin'],data=blob).strip()
        index_lines.append(b'100644 '+oid+b'\t'+name.encode('utf-8')+b'\0')
    git(['update-index','-z','--index-info'],env=env,data=b''.join(index_lines))
    # No push if any sampled project/source bytes changed during collection.
    changed=[name for name,sha in original.items() if not Path(name).is_file() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    if changed: raise RuntimeError('Snapshot inputs changed concurrently; preserve attempt and take a new version: '+str(changed[:8]))
    tree=git(['write-tree'],env=env).decode().strip()
    message=('chore: 🛟 保存 DeepSeek 接管前代码与研究源快照\n\n'
        '保留当前目录重组、项目代码文档及C/E/Z研究源码与交接修复候选。'
        '使用独立备份分支及备用索引，保留原main工作区/暂存区；大型运行数据与活动checkpoint不纳入Git。\n').encode('utf-8')
    csave(outdir/'commit_message.txt',message)
    commit=git(['commit-tree',tree,'-p',base,'-F',str(outdir/'commit_message.txt')],env=env).decode().strip()
    git(['update-ref',ref,commit,'0'*40])
    if git(['rev-parse','HEAD']).decode().strip()!=base: raise RuntimeError('Original HEAD changed unexpectedly')
    index_after=hashlib.sha256(real_index.read_bytes()).hexdigest() if real_index.exists() else None
    if index_after!=original_index_sha: raise RuntimeError('Real index changed unexpectedly')
    result=dict(time=r.now(),commit=commit,tree=tree,branch=branch,ref=ref,base_commit=base,
        project_files=count,external_source_files=len(external),snapshot_virtual_root=backup_root,
        real_working_branch_preserved=current_branch,real_index_byte_exact=True,push_pending=True,
        review_stat=git(['diff-tree','--stat','-M',base,commit]).decode('utf-8',errors='replace')[-4000:])
    csave(outdir/'created_checkpoint.json',r.encoded(result))
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__': main()
