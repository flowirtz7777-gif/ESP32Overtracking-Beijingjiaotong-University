function [targets, report] = generate_evaluation_targets(scenario_csv, opts)
%GENERATE_EVALUATION_TARGETS Frozen interior, right-edge-neighbor and negative strata.
%   Negative labels mean no sampled trailer-body contact within this record.
    if nargin < 2, opts = struct(); end
    here = fileparts(mfilename('fullpath'));
    addpath(fullfile(fileparts(here),'正交路口出弯状态机仿真'));
    if isstruct(scenario_csv)
        scenario = scenario_csv; source_csv = '<in-memory>';
    else
        scenario = load_pid_scenario(scenario_csv); source_csv = char(scenario.csv_path);
    end
    p = vehicle_params(scenario.params);
    defaults = struct('sampling_spacing_m',0.1,'max_boundary_points',7000, ...
        'tolerance_m',0.05,'boundary_band_m',0.2,'negative_margin_m',0.5,'save_outputs',true);
    fields = fieldnames(defaults);
    for i=1:numel(fields)
        if ~isfield(opts,fields{i}), opts.(fields{i})=defaults.(fields{i}); end
    end
    spacing=opts.sampling_spacing_m; maximum=floor(opts.max_boundary_points);
    tolerance=opts.tolerance_m; band=opts.boundary_band_m; margin=opts.negative_margin_m;
    assert(isfinite(spacing) && spacing>0 && isfinite(maximum) && maximum>=3 ...
        && isfinite(tolerance) && tolerance>=0 && isfinite(band) && band>0 ...
        && isfinite(margin) && margin>tolerance,'targets:BadOptions', ...
        'Require positive spacing/band, at least 3 targets, and margin > tolerance.');
    n=numel(scenario.time_s);
    assert(n>0,'targets:EmptyScenario','Empty scenario.');
    frame_count=min(n,max(3,min(80,ceil(maximum/3))));
    frames=local_even_indices(n,frame_count);
    longitudinal=max(3,min(80,ceil(p.L/spacing)+1));
    lateral_count=max(3,min(9,ceil(p.width/spacing)+1));
    pool=cell(3,1);
    for g=1:3, pool{g}=zeros(0,2); end
    for k=frames(:).'
        H=scenario.points.H(k,:); theta=scenario.states.theta_t_rad(k);
        e=[cos(theta),sin(theta)]; normal=[sin(theta),-cos(theta)];
        for j=0:longitudinal-1
            mid=H-p.L*(j/(longitudinal-1))*e;
            inner_mid=H-p.L*((j+0.5)/longitudinal)*e;
            for z=0:lateral_count-1
                offset=(-0.75+1.5*z/(lateral_count-1))*p.width/2;
                pool{1}(end+1,:)=inner_mid+offset*normal; %#ok<AGROW>
            end
            for offset=[-band,0,band]
                pool{2}(end+1,:)=mid+(p.width/2+offset)*normal; %#ok<AGROW>
            end
            for side=[-1,1]
                pool{3}(end+1,:)=mid+side*(p.width/2+margin)*normal; %#ok<AGROW>
            end
        end
    end
    quota=floor(maximum/3)*ones(1,3);
    quota(1:mod(maximum,3))=quota(1:mod(maximum,3))+1;
    names=["interior","boundary","negative"];
    sources=["body_interior","right_edge_neighborhood","near_body"];
    eligible=cell(3,1); contacts=cell(3,1); origins=cell(3,1);
    for g=1:3
        [~,ia]=unique(round(pool{g}/spacing),'rows','stable');
        xy=pool{g}(ia,:);
        xy=xy(local_even_indices(size(xy,1),quota(g)*6),:);
        idx=first_trailer_contacts(xy,scenario,p,tolerance);
        keep=true(size(idx));
        if g==1, keep=isfinite(idx); end
        if g==3, keep=~isfinite(idx); end
        eligible{g}=xy(keep,:); contacts{g}=idx(keep);
        origins{g}=repmat(sources(g),nnz(keep),1);
    end
    if size(eligible{3},1)<quota(3)
        lo=[Inf Inf]; hi=[-Inf -Inf];
        for k=1:n
            H=scenario.points.H(k,:); theta=scenario.states.theta_t_rad(k);
            e=[cos(theta),sin(theta)]; normal=[sin(theta),-cos(theta)];
            corners=[H+p.width/2*normal;H-p.width/2*normal; ...
                     H-p.L*e+p.width/2*normal;H-p.L*e-p.width/2*normal];
            lo=min(lo,min(corners,[],1)); hi=max(hi,max(corners,[],1));
        end
        extra=[repmat(lo(1)-margin,quota(3)*4,1),linspace(lo(2),hi(2),quota(3)*4).'];
        eligible{3}=[eligible{3};extra];
        contacts{3}=[contacts{3};nan(size(extra,1),1)];
        origins{3}=[origins{3};repmat("far_body",size(extra,1),1)];
    end
    xy=zeros(0,2); idx=zeros(0,1); sample_group=strings(0,1); sample_source=strings(0,1);
    used=zeros(0,2);
    for g=1:3
        picks=[local_even_indices(size(eligible{g},1),quota(g)),1:size(eligible{g},1)];
        count=0;
        for j=picks
            key=round(eligible{g}(j,:)/spacing);
            if ismember(key,used,'rows'), continue; end
            used(end+1,:)=key; %#ok<AGROW>
            xy(end+1,:)=eligible{g}(j,:); idx(end+1,1)=contacts{g}(j); %#ok<AGROW>
            sample_group(end+1,1)=names(g); sample_source(end+1,1)=origins{g}(j); %#ok<AGROW>
            count=count+1;
            if count>=quota(g), break; end
        end
    end
    m=size(xy,1); time=nan(m,1); valid=isfinite(idx); time(valid)=scenario.time_s(idx(valid));
    truth_label=repmat("NO_CONTACT_IN_RECORD",m,1); truth_label(valid)="CONTACT";
    target="T"+string((1:m).'); target_set_version=repmat("mixed_v2",m,1);
    targets=table(target,xy(:,1),xy(:,2),time,idx,sample_group,sample_source,truth_label, ...
        target_set_version,repmat(spacing,m,1),repmat(tolerance,m,1),repmat(maximum,m,1), ...
        repmat(band,m,1),repmat(margin,m,1), ...
        'VariableNames',{'target','x_m','y_m','true_contact_time_s','true_contact_idx', ...
        'sample_group','sample_source','truth_label','target_set_version','sampling_spacing_m', ...
        'tolerance_m','max_boundary_points','boundary_band_m','negative_margin_m'});
    report=struct('source_csv',source_csv,'options',opts,'count',m,'output_dir','', ...
        'target_csv','','version','mixed_v2','contact_scope','sampled trailer bodies over full record');
    targets.nearest_contact_edge=nearest_contact_edges(xy,idx,scenario,p);
    if opts.save_outputs
        stamp=char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'));
        report.output_dir=fullfile(here,'logs',['target_set_',stamp]);
        if ~exist(report.output_dir,'dir'), mkdir(report.output_dir); end
        target_dir=fullfile(here,'目标点CSV');
        if ~exist(target_dir,'dir'), mkdir(target_dir); end
        report.target_csv=fullfile(target_dir,['mixed_targets_',stamp,'.csv']);
        writetable(targets,report.target_csv,'Encoding','UTF-8');
        writetable(targets,fullfile(report.output_dir,'targets.csv'),'Encoding','UTF-8');
        fid=fopen(fullfile(report.output_dir,'settings.json'),'w','n','UTF-8');
        clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
        fprintf(fid,'%s',jsonencode(report,'PrettyPrint',true));
    end
end

function idx=local_even_indices(n,limit)
    count=min(n,max(0,floor(limit)));
    if count==0, idx=[]; elseif count==1, idx=1;
    else, idx=round(linspace(1,n,count)); end
end
