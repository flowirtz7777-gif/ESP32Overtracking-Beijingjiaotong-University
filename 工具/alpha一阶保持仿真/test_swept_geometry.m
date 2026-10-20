function report = test_swept_geometry()
%TEST_SWEPT_GEOMETRY Regression tests for temporal OR geometry.
    here = fileparts(mfilename('fullpath'));
    original = pwd;
    cleanup = onCleanup(@() cd(original)); %#ok<NASGU>
    cd(here);
    checks = {};
    large = [0 0; 2 0; 2 2; 0 2; 0 0];
    small = [10 0; 10.2 0; 10.2 0.2; 10 0.2; 10 0];
    disconnected = [large; NaN NaN; small];
    check(all(point_in_poly([1 10.1], [1 0.1], disconnected)), 'small disconnected region retained');
    check(~point_in_poly(5, 0.1, disconnected), 'no bridge between disconnected regions');
    shape = swept_polyshape(disconnected);
    check(abs(area(shape)-4.04) < 1e-9, 'disconnected union area');

    overlap = [large; NaN NaN; large + [1 0]];
    shape = swept_polyshape(overlap);
    check(abs(area(shape)-6) < 1e-9, 'overlap area counted once');
    check(point_in_poly(1.5, 1, overlap), 'overlap uses OR rather than parity cancellation');

    frame = [rect(0,0,3,1); NaN NaN; rect(0,2,3,3); NaN NaN; ...
             rect(0,1,1,2); NaN NaN; rect(2,1,3,2)];
    shape = swept_polyshape(frame);
    check(abs(area(shape)-8) < 1e-9 && ~point_in_poly(1.5,1.5,frame), 'union preserves empty hole');
    rng(42);
    query = rand(100,2)*4-0.5;
    check(isequal(point_in_poly(query(:,1),query(:,2),frame), ...
          isinterior(shape,query(:,1),query(:,2))), 'judge agrees with union away from boundary');

    crossed = swept_segments([0 0; 2 0], [2 2; 0 2]);
    shape = swept_polyshape(crossed);
    check(abs(area(shape)-4) < 1e-9 && point_in_poly(1,1,crossed), 'crossed step uses local convex cover');
    for time = linspace(0,1,11)
        H = [2*time, 0];
        T = [2*(1-time), 2];
        points = H + linspace(0,1,21).' .* (T-H);
        check(all(point_in_poly(points(:,1),points(:,2),crossed)), ...
              sprintf('linear edge interpolation covered %.1f',time));
    end

    stationary = swept_segments([3 4; 3 4], [7 4; 7 4]);
    check(point_in_poly(5,4,stationary) && ~point_in_poly(5,4.1,stationary), 'stationary edge retained without origin fallback');
    check(point_in_poly(5,4.04,stationary,0.05) && ~point_in_poly(5,4.06,stationary,0.05), 'explicit distance tolerance');
    shape = swept_polyshape(stationary);
    check(area(shape)==0, 'degenerate edge has zero area');
    point = swept_segments([3 4], [3 4]);
    check(point_in_poly(3,4,point) && ~point_in_poly(0,0,point), 'degenerate point retained');
    check(isequal(size(point_in_poly([1 3],[1 3],large)),[1 2]), 'query shape preserved');
    check(isempty(point_in_poly([],[],large)), 'empty query');
    check(~any(point_in_poly([0 NaN],[0 NaN],zeros(0,2))), 'empty geometry');
    check(point_in_poly(0,1,large), 'boundary included with numerical tolerance');

    p = vehicle_params();
    s = [0;0;0;0.04];
    short = predict_swept(s,0.15,3,p,1,0.02);
    long = predict_swept(s,0.15,3,p,2,0.02);
    vertices = short(all(isfinite(short),2),:);
    check(all(point_in_poly(vertices(:,1),vertices(:,2),long,1e-8)), 'longer window contains short window on same grid');
    a_short = area(swept_polyshape(short));
    a_long = area(swept_polyshape(long));
    check(a_long >= a_short-1e-9, 'window extension does not reduce union area');
    final = predict_swept([0;0;0;0],0,3,p,0.035,0.02);
    check(point_in_poly(p.l_h+3*0.035,-p.width/2,final), 'partial final step reaches exact horizon');
    initial = predict_swept([0;0;0;0],0,0,p,0,0.02);
    check(point_in_poly(p.l_h,-p.width/2,initial), 'zero horizon retains current edge');

    steps = [0.04 0.02 0.01];
    areas = zeros(size(steps));
    for j = 1:numel(steps)
        areas(j) = area(swept_polyshape(predict_swept(s,0.15,3,p,1,steps(j))));
    end
    check(abs(areas(3)-areas(2)) < abs(areas(2)-areas(1)), 'area converges under step halving');

    folders = {'alpha一阶保持仿真','alpha线性外推仿真','alpha二阶外推仿真', ...
               'alpha多假设并集仿真','alpha扇形包络仿真','正交路口出弯状态机仿真'};
    expected = predict_swept(s,0.15,3,p,1,0.02,0);
    for j = 1:numel(folders)
        cd(fullfile(fileparts(here),folders{j}));
        clear predict_swept point_in_poly swept_segments swept_step_hull swept_polyshape plot_swept_region
        if strcmp(folders{j},'alpha二阶外推仿真')
            actual = predict_swept(s,0.15,3,p,1,0.02,0,0);
        else
            actual = predict_swept(s,0.15,3,p,1,0.02,0);
        end
        check(all(point_in_poly(vertices(:,1),vertices(:,2),actual,1e-8)), ...
              ['shared hold branch retained: ' folders{j}]);
        if ~contains(folders{j},'并集') && ~contains(folders{j},'扇形')
            check(isequaln(actual,expected), ['zero derivatives match hold: ' folders{j}]);
        end
        check(abs(area(swept_polyshape([large;NaN NaN;large+[1 0]]))-6)<1e-9, ...
              ['consistent area helper: ' folders{j}]);
    end
    cd(here);
    clear predict_swept point_in_poly swept_segments swept_step_hull swept_polyshape plot_swept_region
    run_dir = fullfile(here,'runs',[char(datetime('now','Format','yyyyMMdd_HHmmss')) '__swept_geometry_tests']);
    mkdir(run_dir);
    fixtures = struct('name', {}, 'H', {}, 'T', {}, 'queries', {}, 'tolerance', {}, 'expected', {});
    fixture_H = {[0 0;2 0], [3 4;3 4], [3 4;3 4], [0 0;0 1;1 2]};
    fixture_T = {[2 2;0 2], [7 4;7 4], [3 4;3 4], [2 0;2 1;2 3]};
    for fixture_idx = 1:numel(fixture_H)
        H = fixture_H{fixture_idx}; T = fixture_T{fixture_idx};
        queries = [query; 1 1; 5 4; 5 4.04; 5 4.06; 3 4; 0 0];
        fixtures(fixture_idx) = struct('name', sprintf('case_%d',fixture_idx), ...
            'H',H,'T',T,'queries',queries,'tolerance',0.05, ...
            'expected',point_in_poly(queries(:,1),queries(:,2),swept_segments(H,T),0.05));
    end
    fixture_file = fopen(fullfile(run_dir,'web_parity_fixtures.json'),'w');
    fprintf(fixture_file,'%s',jsonencode(fixtures)); fclose(fixture_file);
    fig = figure('Visible','off','Color','white','Position',[80 80 1200 380]);
    subplot(1,3,1); plot_swept_region(disconnected,[0.2 0.6 0.5],'FaceAlpha',0.4);
    axis equal; grid on; title('Disconnected regions retained');
    subplot(1,3,2); plot_swept_region(frame,[0.8 0.3 0.3],'FaceAlpha',0.4);
    axis equal; grid on; title('Overlaps unioned; hole remains empty');
    subplot(1,3,3); plot_swept_region(crossed,[0.2 0.5 0.8],'FaceAlpha',0.4);
    hold on; plot_swept_region(stationary,[0.2 0.2 0.2]); axis equal; grid on;
    title('Crossed and degenerate edges');
    saveas(fig,fullfile(run_dir,'geometry_regression.png')); close(fig);
    report = struct('passed',numel(checks),'checks',{checks},'step_sizes',steps, ...
                    'step_areas',areas,'run_dir',run_dir);
    save(fullfile(run_dir,'report.mat'),'report');
    fid = fopen(fullfile(run_dir,'summary.txt'),'w');
    file_cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid,'Geometry regression: %d checks passed\n',numel(checks));
    fprintf(fid,'Method: segment_convex_union; steering and kinematics unchanged\n');
    fprintf(fid,'Step sizes: %.3f %.3f %.3f s\n',steps);
    fprintf(fid,'Areas: %.9f %.9f %.9f m2\n',areas);
    fprintf(fid,'%s\n',checks{:});
    fprintf('PASSED: %d checks; artifacts: %s\n',numel(checks),run_dir);

    function check(condition,name)
        assert(condition,'swept:testFailed','Failed: %s',name);
        checks{end+1} = name;
    end
end

function points = rect(x1,y1,x2,y2)
    points = [x1 y1; x2 y1; x2 y2; x1 y2; x1 y1];
end
