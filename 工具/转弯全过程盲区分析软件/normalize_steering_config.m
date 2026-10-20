function cfg=normalize_steering_config(cfg)
%NORMALIZE_STEERING_CONFIG Match web inheritance for omitted per-phase steering fields.
    base=normalize_steering_strategy(cfg.strategies.default);
    for key=string(fieldnames(cfg.strategies)).'
        current=cfg.strategies.(key); out=base;
        for field=string(fieldnames(current)).', out.(field)=current.(field); end
        cfg.strategies.(key)=normalize_steering_strategy(out);
    end
end
