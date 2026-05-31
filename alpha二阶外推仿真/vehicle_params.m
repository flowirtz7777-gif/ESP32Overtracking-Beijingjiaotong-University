function p = vehicle_params(varargin)
%VEHICLE_PARAMS  半挂车几何参数 struct（与 C++ Predictor::VehicleParams 对齐）。
%
%   p = vehicle_params()                       使用默认参数
%   p = vehicle_params('l', 4.0, 'L', 13.5)    覆盖特定字段
%   p = vehicle_params(scenario.params)        从 load_pid_scenario 输出直接构造
%
%   字段（单位均为米 / 弧度）：
%     l       牵引车轴距 (前轮 A 到后轴中心 B)
%     l_h     后悬长 (后轴 B 到鞍座牵引销 H)；可正可负，正表示 H 在 B 后方
%     L       挂车轴距 (鞍座 H 到挂车后轴中心 T)
%     width   等效车宽（用于右侧法向偏移 ±width/2）
%     phi_max 铰接角硬限幅 (rad)
%
%   注意：保持与 ArduinoIDE/predictor.h 的 VehicleParams 字段顺序一致，
%   方便后续 C++ 移植时做 1:1 校验。

    % ---------- 默认值 ----------
    defaults = struct( ...
        'l',       4.0, ...
        'l_h',     1.8, ...
        'L',       13.5, ...
        'width',   2.5, ...
        'phi_max', deg2rad(45) ...
    );

    p = defaults;

    if isempty(varargin)
        return;
    end

    % ---------- 单参数：直接传 struct ----------
    if numel(varargin) == 1 && isstruct(varargin{1})
        src = varargin{1};
        % 兼容 load_pid_scenario 的字段名 (l_m / l_h_m / L_m / width_m)
        field_map = struct( ...
            'l',       {{'l', 'l_m'}}, ...
            'l_h',     {{'l_h', 'l_h_m'}}, ...
            'L',       {{'L', 'L_m'}}, ...
            'width',   {{'width', 'width_m'}}, ...
            'phi_max', {{'phi_max', 'phi_max_rad'}} ...
        );
        target_fields = fieldnames(field_map);
        for i = 1:numel(target_fields)
            tf = target_fields{i};
            candidates = field_map.(tf);
            for j = 1:numel(candidates)
                if isfield(src, candidates{j})
                    p.(tf) = double(src.(candidates{j}));
                    break;
                end
            end
        end
        return;
    end

    % ---------- 键值对覆盖 ----------
    if mod(numel(varargin), 2) ~= 0
        error('vehicle_params:BadArgs', '参数必须成对出现 (key, value)');
    end
    for i = 1:2:numel(varargin)
        key = varargin{i};
        val = varargin{i+1};
        if ~isfield(p, key)
            error('vehicle_params:UnknownField', '未知参数字段: %s', key);
        end
        p.(key) = double(val);
    end
end
