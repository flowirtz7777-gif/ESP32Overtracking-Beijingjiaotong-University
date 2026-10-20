function poly = swept_segments(H_right, T_right)
%SWEPT_SEGMENTS NaN-separated local covers; their filled regions are OR-ed.
%   Preserve collinear edges and points for boundary-distance queries.
    if size(H_right, 2) ~= 2 || ~isequal(size(H_right), size(T_right)) || isempty(H_right)
        error('swept:BadEdges', 'Expected matching nonempty N-by-2 edge arrays.');
    end
    count = max(1, size(H_right, 1) - 1);
    pieces = cell(count, 1);
    for k = 1:count
        next = min(k + 1, size(H_right, 1));
        hull = swept_step_hull([H_right(k, :); H_right(next, :); ...
                               T_right(next, :); T_right(k, :)]);
        pieces{k} = [hull; hull(1, :); NaN NaN];
    end
    poly = vertcat(pieces{:});
    poly(end, :) = [];
end
