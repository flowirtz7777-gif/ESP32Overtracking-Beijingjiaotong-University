function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot) %#ok<INUSD>
%PREDICT_SWEPT  [方案 C · 扇形包络] 最坏情况下挂车右外缘可达区域 → 闭合多边形。
%
%   假设方向盘在物理转向速率上限 rate 内可朝任意方向变化：
%       α(τ) ∈ [α_now - rate·τ,  α_now + rate·τ]    （随 τ 张开的锥形）
%   扫掠区 = 该 α 区间扫出的所有车身位置的包络（理论上界，绝不漏报）。
%
%   实现（锥形边界 + 内部采样的并集近似）：
%     在 [α_now-rate·τ, α_now+rate·τ] 内取 N_branch 条分支 α 轨迹，
%     收集所有右外缘点 → polyshape union → 取最大连通区域。
%
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred[, alpha_dot])
%
%   输入：
%     s0,alpha_now,v_now,p,T_h,dt_pred  同基线
%     alpha_dot  本方案忽略（保留以统一签名）
%
%   输出：
%     poly  并集后最大连通区域的闭合多边形 (N×2)
%
%   定位：对照上界模型。扇形包络通常过大（高速时尤甚）、误报多，
%         用于证明"全包络太保守，主模型(方案B)更平衡"。

    rate     = deg2rad(25);   % 方向盘转向速率上限 (rad/s)，与方案 B 回正速率同量级
    N_branch = 7;             % 锥形内采样分支数 (含上/下界与中线)

    % 分支系数 in [-1, 1]：-1=下界(全力反打), 0=保持, +1=上界(全力同向打)
    ks = linspace(-1, 1, N_branch);

    ps_union = [];
    for b = 1:N_branch
        kb = ks(b);
        alpha_fun = @(tau) alpha_now + kb * rate * tau;
        bnd = local_one_branch(s0, alpha_fun, v_now, p, T_h, dt_pred);
        warning('off', 'MATLAB:polyshape:repairedBySimplify');
        ps_b = polyshape(bnd(:,1), bnd(:,2), 'Simplify', true);
        warning('on',  'MATLAB:polyshape:repairedBySimplify');
        if isempty(ps_union)
            ps_union = ps_b;
        else
            ps_union = union(ps_union, ps_b);
        end
    end

    poly = local_largest_region(ps_union);
end


function bnd = local_one_branch(s0, alpha_fun, v_now, p, T_h, dt_pred)
%LOCAL_ONE_BRANCH  单条 α(τ) 分支下的右外缘边界点。
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
