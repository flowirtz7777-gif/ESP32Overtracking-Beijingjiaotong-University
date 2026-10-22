function rates=steering_derivatives(alpha,time,tau)
%STEERING_DERIVATIVES Causal difference/low-pass recursion; no future samples used at k.
    rates=struct('dot',zeros(size(alpha)),'ddot',zeros(size(alpha)));
    filtered=0; second=0;
    for k=2:numel(alpha)
        dt=time(k)-time(k-1);
        assert(dt>0,'steering:BadTime','Scenario times must strictly increase.');
        a=dt/(tau+dt); previous=filtered;
        filtered=filtered+a*((alpha(k)-alpha(k-1))/dt-filtered);
        if k>=3, second=second+a*((filtered-previous)/dt-second); end
        if k>=3, rates.dot(k)=filtered; end
        if k>=4, rates.ddot(k)=second; end
    end
end
