function report=test_evaluation_targets()
%TEST_EVALUATION_TARGETS Verify strata, global contact labels and censored outcomes.
    here=fileparts(mfilename('fullpath')); addpath(here);
    addpath(fullfile(fileparts(here),'正交路口出弯状态机仿真'));
    scenario=struct();
    scenario.time_s=[0;1;5]; scenario.params=struct('l_m',4,'l_h_m',1.8,'L_m',2,'width_m',2);
    scenario.points.H=[0 0;2 0;0 0]; scenario.states.theta_t_rad=zeros(3,1);
    p=vehicle_params(scenario.params);
    queries=[-1 0;1.5 0;8 0;0.03 1.039;0.04 1.04];
    expected=[1;2;NaN;1;2];
    idx=first_trailer_contacts(queries,scenario,p,0.05);
    assert(isequaln(idx,expected),'targets:TestFailed','Global earliest contacts / rounded corners.');
    assert(isequal(nearest_contact_edges(queries,idx,scenario,p), ...
        ["INITIAL_OVERLAP";"FRONT";"NONE";"INITIAL_OVERLAP";"LEFT"]), ...
        'targets:TestFailed','Nearest contact edge descriptors.');
    contact=[5;5;5;0.5;NaN;NaN;NaN];
    warning=[NaN;4.5;3;0.1;1;NaN;4.5]; horizon=2*ones(7,1);
    expected_events=["POLYW_NO_HIT";"BLINDSPOT_REACTION_INSUFFICIENT";"REACTION_TIME_SUFFICIENT"; ...
        "STARTUP_TRUNCATED";"FALSE_POSITIVE";"CORRECT_REJECTION";"END_TRUNCATED"];
    event=classify_warning_events(contact,warning,horizon,5,2,1);
    assert(isequal(event,expected_events),'targets:TestFailed','Seven outcome classes.');
    scope_edges=["FRONT";"FRONT";"FRONT";"FRONT";"FRONT";"NONE";"NONE"];
    scope_events=[repmat("FRONT_CONTACT_IGNORED",4,1);"FALSE_POSITIVE";"CORRECT_REJECTION";"END_TRUNCATED"];
    scoped=classify_warning_events(contact,warning,horizon,5,2,1,scope_edges);
    assert(isequal(scoped,scope_events),'targets:TestFailed','Front exclusion precedes startup and leaves negatives unchanged.');
    for edge=["RIGHT","LEFT","REAR","CORNER","INITIAL_OVERLAP","NONE",""]
        assert(isequal(classify_warning_events(contact,warning,horizon,5,2,1,edge),expected_events), ...
            'targets:TestFailed','Non-front classification unchanged.');
    end
    scope_summary=summarize_contact_edges(table(scope_edges,scoped, ...
        'VariableNames',{'nearest_contact_edge','event'}));
    front_summary=scope_summary(scope_summary.nearest_contact_edge=="FRONT",:);
    assert(front_summary.front_ignored_count==4 && front_summary.eligible_positive==0 && ...
        front_summary.miss_count==0 && isnan(front_summary.insufficient_rate), ...
        'targets:TestFailed','Ignored front samples excluded from numerator and denominator.');
    opts=struct('sampling_spacing_m',0.5,'max_boundary_points',90,'save_outputs',false);
    a=generate_evaluation_targets(scenario,opts); b=generate_evaluation_targets(scenario,opts);
    assert(isequaln(a,b),'targets:TestFailed','Deterministic sampling.');
    assert(height(a)<=90 && all(ismember(["interior";"boundary";"negative"],a.sample_group)), ...
        'targets:TestFailed','Three strata and point budget.');
    assert(size(unique(round([a.x_m,a.y_m]/0.5),'rows'),1)==height(a), ...
        'targets:TestFailed','Cross-stratum spatial deduplication.');
    assert(all(isfinite(a.true_contact_idx(a.sample_group=="interior"))), ...
        'targets:TestFailed','Interior positives independently verified.');
    assert(all(isnan(a.true_contact_idx(a.sample_group=="negative"))), ...
        'targets:TestFailed','Negative candidates verified against full record.');
    rechecked=first_trailer_contacts([a.x_m,a.y_m],scenario,p,0.05);
    assert(isequaln(rechecked,a.true_contact_idx),'targets:TestFailed','All generated labels match truth.');
    bad=false; try, first_trailer_contacts([NaN 0],scenario,p,0.05); catch, bad=true; end
    assert(bad,'targets:TestFailed','Invalid coordinates must not become negatives.');
    bad=false; try, generate_evaluation_targets(scenario,struct('negative_margin_m',0.01,'save_outputs',false)); catch, bad=true; end
    assert(bad,'targets:TestFailed','Negative margin must exceed tolerance.');
    stamp=char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'));
    outdir=fullfile(here,'logs',['target_tests_',stamp]); mkdir(outdir);
    data=struct('time_s',scenario.time_s,'xH_m',scenario.points.H(:,1), ...
        'yH_m',scenario.points.H(:,2),'theta_t_rad',zeros(3,1),'theta_rad',zeros(3,1),'phi_rad',zeros(3,1));
    fixture=struct('data',data,'params',p,'queries',queries,'expected_idx',idx, ...
        'contacts',contact,'warnings',warning,'horizons',horizon,'events',expected_events, ...
        'scope_edges',scope_edges,'scope_events',scope_events, ...
        'generated',table2struct(a(:,{'x_m','y_m','true_contact_idx','sample_group','nearest_contact_edge'})));
    fid=fopen(fullfile(outdir,'target_parity_fixtures.json'),'w','n','UTF-8');
    clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid,'%s',jsonencode(fixture));
    report=struct('passed',20,'generated',height(a),'output_dir',outdir);
    save(fullfile(outdir,'report.mat'),'report');
    fprintf('PASSED: 20 target-set checks; generated=%d; fixtures: %s\n',height(a),outdir);
end
