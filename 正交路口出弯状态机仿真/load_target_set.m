function targets = load_target_set(target_csv_path)
%LOAD_TARGET_SET  读取固定目标集 CSV，返回 N×2 目标中心点 [x,y]。
%
%   targets = load_target_set(path)
%
%   支持列名:
%     x,y
%     x_m,y_m
%     target_x_m,target_y_m
%
%   本函数只读取目标中心点，暂不引入目标宽度。

    if nargin < 1 || isempty(target_csv_path)
        error('load_target_set:MissingPath', '必须传入目标集 CSV 路径');
    end

    target_csv_path = char(target_csv_path);
    if ~isfile(target_csv_path)
        % 允许只传文件名，默认从当前文件夹 targets/ 下找
        this_dir = fileparts(mfilename('fullpath'));
        candidate = fullfile(this_dir, 'targets', target_csv_path);
        if isfile(candidate)
            target_csv_path = candidate;
        else
            error('load_target_set:NotFound', '找不到目标集 CSV: %s', target_csv_path);
        end
    end

    tbl = readtable(target_csv_path, 'VariableNamingRule', 'preserve');
    names = tbl.Properties.VariableNames;

    pairs = {
        'x', 'y';
        'x_m', 'y_m';
        'target_x_m', 'target_y_m'
    };

    x_col = '';
    y_col = '';
    for i = 1:size(pairs, 1)
        if any(strcmp(names, pairs{i,1})) && any(strcmp(names, pairs{i,2}))
            x_col = pairs{i,1};
            y_col = pairs{i,2};
            break;
        end
    end

    if isempty(x_col)
        error('load_target_set:BadColumns', ...
            '目标 CSV 必须包含 x/y、x_m/y_m 或 target_x_m/target_y_m 列');
    end

    targets = [double(tbl.(x_col)), double(tbl.(y_col))];
    targets = targets(all(isfinite(targets), 2), :);
end
