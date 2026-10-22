function s=normalize_steering_strategy(s)
%NORMALIZE_STEERING_STRATEGY Shared defaults for the five experimental modes.
    if ~isfield(s,'alpha_mode'), s.alpha_mode="hold"; end
    s.alpha_mode=string(s.alpha_mode);
    assert(ismember(s.alpha_mode,["hold","linear","quad","union","fan"]),'steering:BadMode','Unsupported mode.');
    tau=0.25; if s.alpha_mode=="quad", tau=0.35; end
    defaults=struct('dt_pred',0.02,'filter_tau_s',tau,'return_rate_deg_s',25, ...
        'fan_rate_deg_s',25,'fan_branches',7,'alpha_limit_deg',40, ...
        'alpha_dot_limit_deg_s',180,'alpha_ddot_limit_deg_s2',360);
    for key=string(fieldnames(defaults)).'
        if ~isfield(s,key), s.(key)=defaults.(key); end
        assert(isfinite(s.(key)) && s.(key)>0,'steering:BadParameter','Invalid steering parameter.');
    end
    assert(s.fan_branches>=3 && s.fan_branches<=31 && mod(s.fan_branches,2)==1 && s.fan_branches==fix(s.fan_branches), ...
        'steering:BadBranches','Fan branch count must be odd, 3..31.');
end
