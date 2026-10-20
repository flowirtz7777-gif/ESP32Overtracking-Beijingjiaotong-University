function inside = points_in_swept_cover(points, edge_seq, tolerance_m)
%POINTS_IN_SWEPT_COVER Vectorized OR of local convex edge covers.
    inside=false(size(points,1),1);
    if iscell(edge_seq)
        for branch=1:numel(edge_seq)
            pending=find(~inside);
            inside(pending)=points_in_swept_cover(points(pending,:),edge_seq{branch},tolerance_m);
        end
        return;
    end
    if isempty(edge_seq) || isempty(points), return; end
    tolerance_m=max(1e-9,tolerance_m);
    for i=1:max(1,numel(edge_seq)-1)
        next=min(i+1,numel(edge_seq));
        hull=swept_step_hull([edge_seq(i).H;edge_seq(next).H;edge_seq(next).T;edge_seq(i).T]);
        lo=min(hull,[],1)-tolerance_m; hi=max(hull,[],1)+tolerance_m;
        pending=find(~inside & points(:,1)>=lo(1) & points(:,1)<=hi(1) ...
            & points(:,2)>=lo(2) & points(:,2)<=hi(2));
        if isempty(pending), continue; end
        inside(pending)=point_in_poly(points(pending,1),points(pending,2),hull,tolerance_m);
        if all(inside), break; end
    end
end
