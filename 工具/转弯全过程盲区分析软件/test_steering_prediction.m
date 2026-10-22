function report=test_steering_prediction()
%TEST_STEERING_PREDICTION Numeric fixtures for independent browser/MATLAB parity.
    root=fileparts(mfilename('fullpath')); addpath(root);
    addpath(fullfile(fileparts(root),'正交路口出弯状态机仿真'));
    time=(0:0.02:0.2).'; alpha=[-0.12;-0.125;-0.131;-0.14;-0.15;-0.145;-0.13;-0.08;-0.06;-0.03;0];
    rates=steering_derivatives(alpha,time,0.25);
    changed=alpha; changed(7:end)=4;
    other=steering_derivatives(changed,time,0.25);
    assert(isequal(rates.dot(1:6),other.dot(1:6)) && isequal(rates.ddot(1:6),other.ddot(1:6)), ...
        'steering:FutureLeak','Future samples changed past rates.');
    p=vehicle_params('l',4,'l_h',1.8,'L',13.5,'width',2,'phi_max',deg2rad(15));
    state=[2 -3 0.5 -0.1]; k=6; horizon=1.13;
    cases=struct('strategy',{},'branches',{});
    for mode=["hold","linear","quad","union","fan"]
        s=normalize_steering_strategy(struct('alpha_mode',mode,'dt_pred',0.02,'filter_tau_s',0.25));
        branches=predict_steering_edges(state,alpha(k),3,p,horizon,s,rates.dot(k),rates.ddot(k));
        expected=1; if mode=="union", expected=3; elseif mode=="fan", expected=7; end
        assert(numel(branches)==expected);
        assert(all(cellfun(@numel,branches)==58));
        for b=1:numel(branches), assert(all(isfinite(vertcat(branches{b}.H)),'all')); end
        cases(end+1)=struct('strategy',s,'branches',{branches}); %#ok<AGROW>
    end
    a=struct('H',[0 0],'T',[1 0]); b=struct('H',[0 1],'T',[1 1]);
    c=struct('H',[10 0],'T',[11 0]); d=struct('H',[10 1],'T',[11 1]);
    hits=points_in_swept_cover([0.5 0.5;10.5 0.5;5 0.5],{[a;b],[c;d]},0);
    assert(isequal(hits,[true;true;false]),'steering:BranchBridge','Geometry connected separate branches.');
    stamp=char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'));
    out=fullfile(root,'logs',['steering_tests_',stamp]); mkdir(out);
    fixture=struct('time',time,'alpha',alpha,'rates',rates,'params',p,'state',state,'k',k,'horizon',horizon,'cases',cases);
    fid=fopen(fullfile(out,'steering_parity.json'),'w','n','UTF-8'); clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid,'%s',jsonencode(fixture));
    report=struct('passed',true,'output_dir',out); save(fullfile(out,'report.mat'),'report');
    fprintf('PASSED native steering causality, branch counts, partial horizon and no-bridge checks: %s\n',out);
end
