function branches=predict_steering_edges(s0,alpha,v,p,horizon,strategy,alpha_dot,alpha_ddot)
%PREDICT_STEERING_EDGES Separate edge sequences; geometry must OR, never bridge branches.
    s=normalize_steering_strategy(strategy);
    count=max(0,ceil(horizon/s.dt_pred-1e-10));
    number=1;
    if s.alpha_mode=="union", number=3; elseif s.alpha_mode=="fan", number=s.fan_branches; end
    alpha_dot=max(-deg2rad(s.alpha_dot_limit_deg_s),min(deg2rad(s.alpha_dot_limit_deg_s),alpha_dot));
    alpha_ddot=max(-deg2rad(s.alpha_ddot_limit_deg_s2),min(deg2rad(s.alpha_ddot_limit_deg_s2),alpha_ddot));
    branches=cell(number,1);
    for branch=1:number
        state=s0; seq=repmat(struct('H',[0 0],'T',[0 0]),count+1,1);
        for i=0:count
            d=derive_points(state,p); n=[sin(d.theta_t),-cos(d.theta_t)];
            seq(i+1).H=d.H+p.width/2*n; seq(i+1).T=d.T+p.width/2*n;
            if i<count
                tau=i*s.dt_pred; value=alpha;
                if s.alpha_mode=="linear" || (s.alpha_mode=="union" && branch==2)
                    value=value+alpha_dot*tau;
                elseif s.alpha_mode=="quad"
                    value=value+alpha_dot*tau+0.5*alpha_ddot*tau^2;
                elseif s.alpha_mode=="union" && branch==3 && abs(alpha)>=deg2rad(1)
                    value=sign(alpha)*max(0,abs(alpha)-deg2rad(s.return_rate_deg_s)*tau);
                elseif s.alpha_mode=="fan"
                    value=value+(2*(branch-1)/(s.fan_branches-1)-1)*deg2rad(s.fan_rate_deg_s)*tau;
                end
                if s.alpha_mode~="hold", value=max(-deg2rad(s.alpha_limit_deg),min(deg2rad(s.alpha_limit_deg),value)); end
                delta=min(s.dt_pred,horizon-i*s.dt_pred);
                if abs(delta-s.dt_pred)<1e-10, delta=s.dt_pred; end
                state=kinematics_step(state,value,v,p,delta);
            end
        end
        branches{branch}=seq;
    end
end
