function alpha_dot = estimate_alpha_dot(alpha_series, k, dt, lpf_tau)
%ESTIMATE_ALPHA_DOT  在第 k 个采样点估计 α 的变化率（LPF 后）。
%
%   alpha_dot = estimate_alpha_dot(alpha_series, k, dt, lpf_tau)
%
%   输入：
%     alpha_series  整段 α(t) 序列 (rad)，列或行向量
%     k             当前采样索引 (1-based)
%     dt            采样步长 (s)
%     lpf_tau       一阶低通时间常数 (s)，建议 0.2~0.3；越大越平滑
%
%   输出：
%     alpha_dot     LPF 后的 α 变化率 (rad/s)
%
%   说明（方案 A：线性外推 α(τ)=α₀+α̇·τ 的关键前置）：
%     - 原始差分 dα/dt 在 PID 输出含高频抖动时噪声极大，直接拿去做 2 秒
%       外推会让扫掠多边形发散（v1.0.1 踩过的坑）。
%     - 这里对差分序列做因果一阶低通：用 k 之前的窗口估计，符合实车
%       "只能用历史"的在线约束。
%     - 端点退化（k<3）时返回 0。

    n = numel(alpha_series);
    if k < 3 || k > n
        alpha_dot = 0;
        return;
    end

    % 因果一阶低通滤波器系数
    a = dt / (lpf_tau + dt);   % 0<a<1，lpf_tau 越大 a 越小越平滑

    % 从序列起点滤到 k（在线可用：只用历史）
    ad_filt = 0;
    for i = 2:k
        raw = (alpha_series(i) - alpha_series(i-1)) / dt;
        ad_filt = ad_filt + a * (raw - ad_filt);
    end
    alpha_dot = ad_filt;
end
