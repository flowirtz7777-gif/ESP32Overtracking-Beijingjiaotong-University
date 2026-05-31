function out = plot_threshold_filtered_blindspots(scan_dir, max_thresholds)
%PLOT_THRESHOLD_FILTERED_BLINDSPOTS  从 threshold_scan_points.csv 重绘阈值过滤盲区图。
%
%   out = plot_threshold_filtered_blindspots(scan_dir, [2.0 1.5 1.0])

    if nargin < 1 || isempty(scan_dir)
        script_dir = fileparts(mfilename('fullpath'));
        d = dir(fullfile(script_dir, 'logs', 'threshold_scan_*'));
        if isempty(d)
            error('plot_threshold_filtered_blindspots:NoScanDir', '未找到 threshold_scan_* 输出目录。');
        end
        [~, idx] = max([d.datenum]);
        scan_dir = fullfile(d(idx).folder, d(idx).name);
    end
    if nargin < 2 || isempty(max_thresholds)
        max_thresholds = [2.0 1.5 1.0];
    end

    points_path = fullfile(scan_dir, 'threshold_scan_points.csv');
    if ~exist(points_path, 'file')
        error('plot_threshold_filtered_blindspots:NoPointsCsv', '未找到 %s', points_path);
    end

    tbl = readtable(points_path, 'TextType', 'string');
    out = struct();
    out.scan_dir = scan_dir;
    out.files = strings(numel(max_thresholds), 1);

    for i = 1:numel(max_thresholds)
        max_t = max_thresholds(i);
        fig = local_plot_one(tbl, max_t);
        out_path = fullfile(scan_dir, sprintf('threshold_blindspot_overlay_le_%.1fs.png', max_t));
        fig_path = fullfile(scan_dir, sprintf('threshold_blindspot_overlay_le_%.1fs.fig', max_t));
        exportgraphics(fig, out_path, 'Resolution', 220);
        savefig(fig, fig_path);
        close(fig);
        out.files(i) = string(out_path);
        fprintf('[FILTER] %.1fs: %s\n', max_t, out_path);
    end
end


function fig = local_plot_one(tbl, max_threshold_s)
    fig = figure('Name', sprintf('Blindspots <= %.1fs', max_threshold_s), ...
        'Color', 'white', 'Position', [80 80 1120 820]);
    ax = axes(fig);
    hold(ax, 'on'); grid(ax, 'on'); axis(ax, 'equal');

    startup = local_as_logical(tbl.is_startup_truncated);
    no_warning_col = local_as_logical(tbl.is_no_warning);
    no_warn = ~startup & no_warning_col;
    valid_blind = ~startup & ~tbl.is_no_warning & ...
        ~isnan(tbl.critical_threshold_s) & tbl.critical_threshold_s <= max_threshold_s;

    if any(startup)
        scatter(ax, tbl.x_m(startup), tbl.y_m(startup), 10, [0.72 0.76 0.84], 'filled', ...
            'MarkerFaceAlpha', 0.18, 'DisplayName', 'STARTUP_TRUNCATED');
    end
    if any(no_warn)
        scatter(ax, tbl.x_m(no_warn), tbl.y_m(no_warn), 24, 'k', 'x', ...
            'LineWidth', 1.0, 'DisplayName', 'PolyW未命中');
    end
    if any(valid_blind)
        scatter(ax, tbl.x_m(valid_blind), tbl.y_m(valid_blind), 22, tbl.critical_threshold_s(valid_blind), ...
            'filled', 'MarkerFaceAlpha', 0.82, 'DisplayName', sprintf('盲区点 <= %.1fs', max_threshold_s));
    end

    colormap(ax, flipud(turbo));
    cb = colorbar(ax);
    cb.Label.String = '首次成为盲区的反应时间阈值 / s';
    clim(ax, [0.1, max(0.1, max_threshold_s)]);

    xlabel(ax, 'X (m)');
    ylabel(ax, 'Y (m)');
    title(ax, {sprintf('盲区点过滤分布：临界阈值 <= %.1f s', max_threshold_s), ...
        sprintf('显示点数=%d，不含起始截断；黑叉=PolyW未命中', nnz(valid_blind))}, ...
        'FontWeight', 'bold');
    legend(ax, 'Location', 'bestoutside');
end


function out = local_as_logical(v)
    if islogical(v)
        out = v;
    elseif isnumeric(v)
        out = v ~= 0;
    else
        out = string(v) == "1" | lower(string(v)) == "true";
    end
end
