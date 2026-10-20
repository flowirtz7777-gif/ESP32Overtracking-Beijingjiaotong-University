function report=test_legacy_phi_parity(run_dir)
%TEST_LEGACY_PHI_PARITY Verify missing metadata uses the same assumed 15deg as the web.
    root=fileparts(mfilename('fullpath')); addpath(root);
    rows=jsondecode(fileread(fullfile(run_dir,'summary.json')));
    source=fullfile(run_dir,'scenarios','legacy_phi','scenario.csv');
    targets=fullfile(run_dir,'scenarios','legacy_phi','targets.csv');
    details=cell(numel(rows),1);
    for i=1:numel(rows)
        cfg=fullfile(fileparts(rows(i).result_csv),'cfg_effective.json');
        r=validate_turn_exit_targets(source,targets,rows(i).result_csv,0.05,2,cfg,1);
        assert(abs(r.params.phi_max-deg2rad(15))<1e-12,'steering:BadFallback','Legacy phi default differs from web.');
        assert(all(r.compare.web_event==r.compare.matlab_event),'steering:Mismatch','Legacy CSV event mismatch.');
        d=r.compare.diff_first_PolyW_s;
        assert(all(abs(d(isfinite(d)))<1e-6));
        assert(nnz(isfinite(r.compare.web_first_PolyW_s))==nnz(isfinite(r.compare.matlab_first_PolyW_s)));
        details{i}=struct('mode',rows(i).alpha_mode_default,'passed',true,'run_dir',r.run_dir);
    end
    report=struct('passed',true,'details',{details});
    fid=fopen(fullfile(run_dir,'legacy_native_parity.json'),'w','n','UTF-8');
    clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid,'%s',jsonencode(report));
    fprintf('PASSED legacy missing-phi metadata parity for all five modes.\n');
end
