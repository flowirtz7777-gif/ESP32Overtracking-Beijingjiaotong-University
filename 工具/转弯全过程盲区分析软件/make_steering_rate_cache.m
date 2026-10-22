function cache=make_steering_rate_cache(alpha,time,cfg)
%MAKE_STEERING_RATE_CACHE Filter each configured strategy once per replay.
    cache=struct();
    for key=string(fieldnames(cfg.strategies)).'
        s=normalize_steering_strategy(cfg.strategies.(key));
        cache.(key)=steering_derivatives(alpha,time,s.filter_tau_s);
    end
end
