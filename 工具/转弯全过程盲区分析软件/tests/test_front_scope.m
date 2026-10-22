function report = test_front_scope(browser_run_dir)
%TEST_FRONT_SCOPE Cross-check the frozen 700-target browser run and threshold scans.
    root = fileparts(fileparts(mfilename('fullpath')));
    addpath(root);
    d = fullfile(root,browser_run_dir);
    cfg = fullfile(root,'CFG配置','exit_window_test_cfg.json');
    scenario = fullfile(d,'builtin_scenario.csv');
    targets = fullfile(d,'web_targets.csv');
    web_log = fullfile(d,'web_log.csv');
    r = validate_turn_exit_targets(scenario,targets,web_log,0.05,2,cfg,1);
    assert(nnz(r.table.event=="FRONT_CONTACT_IGNORED")==198);
    assert(nnz(r.table.event=="POLYW_NO_HIT")==0);
    assert(nnz(r.table.event=="BLINDSPOT_REACTION_INSUFFICIENT")==2);
    assert(nnz(r.table.event=="REACTION_TIME_SUFFICIENT")==184);
    assert(all(r.compare.matlab_event==r.compare.web_event));
    assert(all(abs(r.compare.diff_first_PolyW_s(isfinite(r.compare.diff_first_PolyW_s)))<1e-9));
    opts = struct('target_csv',targets,'strategy_cfg_json',cfg,'thresholds_s',[0.5 1 2]);
    s = scan_ttc_threshold_blindspots(scenario,opts);
    assert(all(s.counts.front_ignored_count==198));
    assert(all(s.counts.miss_count==0));
    assert(all(s.counts.positive_count==186));
    assert(all(s.counts.false_positive_count==7));
    assert(s.counts.late_count(s.counts.reaction_threshold_s==1)==2);
    assert(all(isnan(s.points.critical_threshold_s(s.points.is_front_contact_ignored))));
    assert(~any(s.points.is_no_warning(s.points.is_front_contact_ignored)));
    filtered = plot_threshold_filtered_blindspots(s.out_dir,1);
    close all;
    report = struct('passed',true,'validation_dir',r.run_dir,'scan_dir',s.out_dir,'filtered',filtered.files);
    fid = fopen(fullfile(d,'matlab_scope_report.json'),'w','n','UTF-8');
    clean = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid,'%s',jsonencode(report));
    fprintf('PASSED MATLAB front scope, browser parity, threshold scan and filtered plot.\n');
end
