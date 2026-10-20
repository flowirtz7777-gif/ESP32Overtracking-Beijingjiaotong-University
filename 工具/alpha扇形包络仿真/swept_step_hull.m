function hull = swept_step_hull(points)
%SWEPT_STEP_HULL Local convex cover of one linearly interpolated edge step.
    points = unique(points, 'rows');
    if isempty(points) || size(points, 2) ~= 2 || any(~isfinite(points), 'all')
        error('swept:BadPoints', 'Expected finite N-by-2 edge points.');
    end
    if size(points, 1) == 1
        hull = points;
        return;
    end
    offset = points - points(1, :);
    if size(points, 1) >= 3 && rank(offset, 1e-12) >= 2
        idx = convhull(points(:, 1), points(:, 2));
        hull = points(idx(1:end-1), :);
    else
        [~, far] = max(sum(offset.^2, 2));
        direction = offset(far, :);
        projection = offset * direction.';
        [~, first] = min(projection);
        [~, last] = max(projection);
        hull = points([first, last], :);
    end
end
