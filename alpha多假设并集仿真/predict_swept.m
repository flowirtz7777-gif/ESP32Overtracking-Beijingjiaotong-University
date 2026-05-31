function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%PREDICT_SWEPT  [方案 B · 多假设并集] 挂车右侧外缘扫过区域 → 闭合多边形。
%
%   不赌单一未来，而是同时演化三种 α(τ) 假设，取扫掠区的并集：
%     假设1 (保持):     α(τ) = α_now
%     假设2 (继续打):   α(τ) = α_now + alpha_dot·τ      （沿当前趋势）
%     假设3 (开始回正): α(τ) = α_now - sign(α_now)·rate·τ（朝 0 回）
%   最终危险区 = Poly(假设1) ∪ Poly(假设2) ∪ Poly(假设3)
%
%   安全工程思路：不预测司机意图，而是覆盖所有合理意图 → 宁可多覆盖不漏报。
%
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%
%   输入：
%     s0        初始状态 [xB, yB, theta, phi]
%     alpha_now 当前前轮转向角 (rad)
%     v_now     当前车速 (m/s)
%     p         vehicle_params struct
%     T_h       预测时间窗 (s)
%     dt_pred   预测内部步长 (s)
%     alpha_dot (可选) LPF 后转向角速率 (rad/s)，用于假设2
%
%   输出：
%     poly  并集后最大连通区域的闭合多边形 (N×2)，最后一行 = 第一行
%
%   说明：
%     - 三个假设的扫掠区在 τ=0 处共享同一条起始车身右沿，通常连成一块。
%     - union 后若出现多块，取面积最大者（与基线 polyshape 处理一致）。

    if nargin < 7, alpha_dot = 0; end
    if isempty(alpha_dot) || ~isfinite(alpha_dot), alpha_dot = 0; end
    ALPHA_DOT_MAX = pi;
    if abs(alpha_dot) > ALPHA_DOT_MAX
        alpha_dot = sign(alpha_dot) * ALPHA_DOT_MAX;
    end

    % 假设3 的回正速率：若当前几乎直行则不回正（避免符号抖动）
    return_rate = deg2rad(25);     % 25°/s 朝 0 回（典型驾驶员回方向速率量级）
    if abs(alpha_now) < deg2rad(1)
        sign_a = 0;
    else
        sign_a = sign(alpha_now);
    end

    % 三个假设的 α(τ) 函数句柄
    hypo = {
        @(tau) alpha_now;                                  % 假设1 保持
        @(tau) alpha_now + alpha_dot * tau;                % 假设2 继续打
        @(tau) alpha_now - sign_a * return_rate * tau      % 假设3 回正
    };

    ps_union = [];
    for h = 1:numel(hypo)
        bnd = local_one_hypothesis(s0, hypo{h}, v_now, p, T_h, dt_pred);
        warning('off', 'MATLAB:polyshape:repairedBySimplify');
        ps_h = polyshape(bnd(:,1), bnd(:,2), 'Simplify', true);
        warning('on',  'MATLAB:polyshape:repairedBySimplify');
        if isempty(ps_union)
            ps_union = ps_h;
        else
            ps_union = union(ps_union, ps_h);
        end
    end

    poly = local_largest_region(ps_union);
end


function bnd = local_one_hypothesis(s0, alpha_fun, v_now, p, T_h, dt_pred)
%LOCAL_ONE_HYPOTHESIS  单个 α(τ) 假设下的右外缘边界点（未做 polyshape 简化）。
    half_w = 0.5 * p.width;
    M = floor(T_h / dt_pred);
    H_right = zeros(M+1, 2);
    T_right = zeros(M+1, 2);
    s = s0(:);
    tau = 0;
    for k = 1:M+1
        d = derive_points(s, p);
        cTt = cos(d.theta_t); sTt = sin(d.theta_t);
        H_right(k, :) = d.H + half_w * [ sTt, -cTt ];
        T_right(k, :) = d.T + half_w * [ sTt, -cTt ];
        if k <= M
            alpha_tau = alpha_fun(tau);
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s = kinematics_step(s, alpha_tau, v_now, p, dt_pred);
            tau = tau + dt_pred;
        end
    end
    bnd = [H_right; flipud(T_right)];
end


function poly = local_largest_region(ps)
%LOCAL_LARGEST_REGION  从 polyshape 取面积最大的连通区域，返回闭合 N×2。
    try
        if ps.NumRegions <= 0
            poly = [0 0; 0 0; 0 0];
            return;
        end
        if ps.NumRegions == 1
            bx = ps.Vertices(:,1); by = ps.Vertices(:,2);
        else
            regs = regions(ps);
            areas = arrayfun(@area, regs);
            [~, idx] = max(areas);
            bx = regs(idx).Vertices(:,1);
            by = regs(idx).Vertices(:,2);
        end
        bx = bx(~isnan(bx)); by = by(~isnan(by));
        poly = [bx, by];
        if size(poly,1) >= 3 && ~isequal(poly(1,:), poly(end,:))
            poly = [poly; poly(1,:)];
        end
    catch
        poly = [0 0; 0 0; 0 0];
    end
end
