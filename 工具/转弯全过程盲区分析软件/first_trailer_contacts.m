function idx = first_trailer_contacts(points, scenario, p, tolerance_m)
%FIRST_TRAILER_CONTACTS Earliest sampled body contact across the entire record.
%   Uses Euclidean rectangle distance, including rounded tolerance at corners.
    if nargin < 4, tolerance_m = 0.05; end
    validateattributes(points,{'numeric'},{'2d','ncols',2,'real','finite'});
    validateattributes(tolerance_m, {'numeric'}, {'scalar','real','finite','nonnegative'});
    idx = nan(size(points,1),1);
    tolerance_m = max(1e-9,tolerance_m);
    for k = 1:numel(scenario.time_s)
        pending = find(isnan(idx));
        if isempty(pending), break; end
        H = scenario.points.H(k,:);
        theta = scenario.states.theta_t_rad(k);
        delta = points(pending,:)-H;
        along = delta(:,1)*cos(theta)+delta(:,2)*sin(theta);
        lateral = delta(:,1)*sin(theta)-delta(:,2)*cos(theta);
        outside_long = max([zeros(numel(pending),1), along, -p.L-along],[],2);
        outside_lat = max(0,abs(lateral)-p.width/2);
        hit = outside_long.^2+outside_lat.^2 <= tolerance_m^2;
        idx(pending(hit)) = k;
    end
end
