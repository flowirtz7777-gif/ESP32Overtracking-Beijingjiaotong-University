function report=test_browser_steering_parity(pilot_dir)
%TEST_BROWSER_STEERING_PARITY Recompute all five 90-point browser runs with native MATLAB.
    root=fileparts(mfilename('fullpath')); addpath(root);
    rows=jsondecode(fileread(fullfile(pilot_dir,'summary.json')));
    scenario=fullfile(pilot_dir,'scenarios','builtin','scenario.csv');
    targets=fullfile(pilot_dir,'scenarios','builtin','targets.csv');
    reports=cell(numel(rows),1);
    for i=1:numel(rows)
        cfg=fullfile(fileparts(rows(i).result_csv),'cfg_effective.json');
        r=validate_turn_exit_targets(scenario,targets,rows(i).result_csv,0.05,2,cfg,1);
        assert(all(r.compare.web_event==r.compare.matlab_event),'steering:ClassificationMismatch','Web/native classification differs.');
        difference=r.compare.diff_first_PolyW_s;
        assert(all(abs(difference(isfinite(difference)))<1e-6),'steering:TimeMismatch','First warning times differ.');
        assert(nnz(isfinite(r.compare.web_first_PolyW_s))==nnz(isfinite(r.compare.matlab_first_PolyW_s)), ...
            'steering:HitMismatch','Finite hits differ.');
        reports{i}=struct('mode',rows(i).alpha_mode_default,'run_dir',r.run_dir,'passed',true);
    end
    report=struct('passed',true,'modes',{reports});
    fid=fopen(fullfile(pilot_dir,'native_parity_report.json'),'w','n','UTF-8');
    clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid,'%s',jsonencode(report));
    fprintf('PASSED full web/MATLAB warning-time and event parity for all five modes.\n');
end
