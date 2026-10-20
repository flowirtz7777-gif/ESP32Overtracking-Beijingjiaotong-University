function edges=nearest_contact_edges(points,idx,scenario,p)
%NEAREST_CONTACT_EDGES Descriptive nearest edge at sampled contact, not entry-face proof.
    edges=repmat("NONE",size(idx));
    names=["RIGHT","LEFT","FRONT","REAR"];
    for i=find(isfinite(idx)).'
        k=idx(i);
        if k==1, edges(i)="INITIAL_OVERLAP"; continue; end
        theta=scenario.states.theta_t_rad(k); delta=points(i,:)-scenario.points.H(k,:);
        along=delta(1)*cos(theta)+delta(2)*sin(theta);
        lateral=delta(1)*sin(theta)-delta(2)*cos(theta);
        outlong=max([0,along,-p.L-along]); outlat=max(0,abs(lateral)-p.width/2);
        distance=[hypot(outlong,lateral-p.width/2),hypot(outlong,lateral+p.width/2), ...
                  hypot(along,outlat),hypot(along+p.L,outlat)];
        near=find(distance<=min(distance)+1e-9);
        if numel(near)>1, edges(i)="CORNER"; else, edges(i)=names(near); end
    end
end
