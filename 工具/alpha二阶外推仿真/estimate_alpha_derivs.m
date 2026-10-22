function [alpha_dot, alpha_ddot] = estimate_alpha_derivs(alpha_series, k, dt, lpf_tau)
%ESTIMATE_ALPHA_DERIVS  估计 α 的一阶 α̇ 与二阶 α̈ 变化率（均 LPF 后）。
%
%   [alpha_dot, alpha_ddot] = estimate_alpha_derivs(alpha_series, k, dt, lpf_tau)
%
%   输入：
%     alpha_series  整段 α(t) 序列 (rad)
%     k             当前采样索引 (1-based)
%     dt            采样步长 (s)
%     lpf_tau       一阶低通时间常数 (s)，建议 0.3~0.4（二阶对噪声更敏感，要更平滑）
%
%   输出：
%     alpha_dot     LPF 后 α 一阶变化率 (rad/s)
%     alpha_ddot    LPF 后 α 二阶变化率 (rad/s²)
%
%   说明（方案 D：二阶外推 α(τ)=α₀+α̇·τ+½·α̈·τ² 的前置）：
%     - 二阶差分对噪声极敏感，必须用比方案 A 更强的低通。
%     - 因果实现：只用 k 之前的历史，符合在线约束。
%     - 端点退化时返回 0。

    n = numel(alpha_series);
    if k < 4 || k > n
        alpha_dot = 0;
        alpha_ddot = 0;
        return;
    end

    a = dt / (lpf_tau + dt);

    % 先在线滤出 α̇ 序列，再对 α̇ 滤一次得到 α̈
    ad_filt = 0;
    ad_prev = 0;
    add_filt = 0;
    for i = 2:k
        raw_ad = (alpha_series(i) - alpha_series(i-1)) / dt;
        ad_prev = ad_filt;
        ad_filt = ad_filt + a * (raw_ad - ad_filt);
        if i >= 3
            raw_add = (ad_filt - ad_prev) / dt;
            add_filt = add_filt + a * (raw_add - add_filt);
        end
    end
    alpha_dot  = ad_filt;
    alpha_ddot = add_filt;
end
