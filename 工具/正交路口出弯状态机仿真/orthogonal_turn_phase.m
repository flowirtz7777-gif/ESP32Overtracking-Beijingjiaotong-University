function phase = orthogonal_turn_phase(theta, alpha, phi, dt, state_machine)
%ORTHOGONAL_TURN_PHASE  正交路口转弯阶段识别（离线复盘版，因果量）。
%
%   phase = orthogonal_turn_phase(theta, alpha, phi, dt)
%   phase = orthogonal_turn_phase(theta, alpha, phi, dt, state_machine)
%
%   输出 phase:
%     0 = IDLE / 尚未进入有效转弯
%     1 = ENTRY / 入弯
%     2 = MID / 转弯中
%     3 = EXIT / 出弯
%     4 = DONE / 转弯结束
%
%   设计边界:
%     - 面向十字正交路口，使用累计航向变化接近 90° 作为 EXIT 强证据。
%     - 当前没有真实转向灯输入，用 |alpha| 阈值模拟“开始转弯”触发。
%     - 状态机带进入/退出计数滞回，避免在阈值附近抖动。

    N = numel(theta);
    phase = zeros(N, 1);
    if N == 0, return; end

    if nargin < 5 || isempty(state_machine)
        state_machine = struct();
    end

    alpha_start_th = deg2rad(local_field(state_machine, 'alpha_start_deg', 2.0));
    alpha_done_th  = deg2rad(local_field(state_machine, 'done_alpha_abs_deg_max', 1.0));
    phi_done_th    = deg2rad(local_field(state_machine, 'done_phi_abs_deg_max', 2.0));
    mid_heading_th = deg2rad(local_field(state_machine, 'mid_heading_delta_deg', 25.0));
    exit_heading_th = deg2rad(local_field(state_machine, 'exit_heading_delta_deg_min', 75.0));
    done_heading_th = deg2rad(local_field(state_machine, 'done_heading_delta_deg_min', 88.0));
    phi_lag_th      = deg2rad(local_field(state_machine, 'exit_phi_abs_deg_min', 4.0));
    require_alpha_returning = logical(local_field(state_machine, 'exit_require_alpha_returning', true));

    enter_count_need = round(local_field(state_machine, 'enter_hold_frames', 2));
    exit_count_need  = round(local_field(state_machine, 'exit_hold_frames', 2));
    done_count_need  = round(local_field(state_machine, 'done_hold_frames', 10));
    enter_count_need = max(1, enter_count_need);
    exit_count_need = max(1, exit_count_need);
    done_count_need = max(1, done_count_need);

    state = 0;
    theta_start = theta(1);
    turn_sign = 0;
    enter_count = 0;
    exit_count = 0;
    done_count = 0;

    alpha_dot = [0; diff(alpha(:)) ./ dt];
    theta_unwrap = unwrap(theta(:));

    for k = 1:N
        a = alpha(k);
        ph = phi(k);

        switch state
            case 0  % IDLE
                if abs(a) >= alpha_start_th
                    enter_count = enter_count + 1;
                else
                    enter_count = 0;
                end
                if enter_count >= enter_count_need
                    state = 1;
                    theta_start = theta_unwrap(k);
                    turn_sign = sign(a);
                    if turn_sign == 0, turn_sign = 1; end
                    exit_count = 0;
                    done_count = 0;
                end

            case 1  % ENTRY
                delta_heading = turn_sign * (theta_unwrap(k) - theta_start);
                if delta_heading >= mid_heading_th
                    state = 2;
                end

            case 2  % MID
                delta_heading = turn_sign * (theta_unwrap(k) - theta_start);
                alpha_returning = (a * alpha_dot(k) < 0) && abs(a) > alpha_done_th;
                trailer_lagging = abs(ph) >= phi_lag_th;
                exit_candidate = (delta_heading >= exit_heading_th) && ...
                                 ((require_alpha_returning && alpha_returning) || trailer_lagging || ~require_alpha_returning);
                if exit_candidate
                    exit_count = exit_count + 1;
                else
                    exit_count = 0;
                end
                if exit_count >= exit_count_need
                    state = 3;
                    done_count = 0;
                end

            case 3  % EXIT
                delta_heading = turn_sign * (theta_unwrap(k) - theta_start);
                done_candidate = (delta_heading >= done_heading_th) && ...
                                 abs(a) <= alpha_done_th && ...
                                 abs(ph) <= phi_done_th;
                if done_candidate
                    done_count = done_count + 1;
                else
                    done_count = 0;
                end
                if done_count >= done_count_need
                    state = 4;
                end

            case 4  % DONE
                % 保持 DONE，不在同一段工况内重入。
        end

        phase(k) = state;
    end
end


function value = local_field(s, name, default_value)
    if isfield(s, name) && ~isempty(s.(name))
        value = s.(name);
    else
        value = default_value;
    end
end
