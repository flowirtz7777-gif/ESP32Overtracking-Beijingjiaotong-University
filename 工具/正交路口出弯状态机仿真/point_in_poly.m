function inside = point_in_poly(px, py, poly, tolerance_m)
%POINT_IN_POLY OR all NaN-separated pieces, including degenerate boundaries.
%   Default 1e-9 m is numerical tolerance, not a physical safety expansion.
    if nargin < 4, tolerance_m = 1e-9; end
    validateattributes(tolerance_m, {'numeric'}, {'scalar', 'real', 'finite', 'nonnegative'});
    original_size = size(px);
    px = px(:);
    py = py(:);
    if numel(px) ~= numel(py)
        error('point_in_poly:BadQuery', 'Query coordinates must have equal length.');
    end
    inside = false(size(px));
    breaks = [0; find(any(~isfinite(poly), 2)); size(poly, 1) + 1];
    for k = 1:numel(breaks)-1
        piece = poly(breaks(k)+1:breaks(k+1)-1, :);
        if isempty(piece), continue; end
        if size(piece, 1) > 1 && isequal(piece(1, :), piece(end, :))
            piece(end, :) = [];
        end
        pending = find(~inside);
        if isempty(pending), break; end
        x = px(pending);
        y = py(pending);
        hit = false(size(x));
        min_d2 = inf(size(x));
        j = size(piece, 1);
        for i = 1:size(piece, 1)
            a = piece(j, :);
            b = piece(i, :);
            crossing = (a(2) > y) ~= (b(2) > y);
            if a(2) ~= b(2)
                hit = xor(hit, crossing & x < a(1) + (y-a(2)) .* (b(1)-a(1)) ./ (b(2)-a(2)));
            end
            delta = b-a;
            length2 = sum(delta.^2);
            if length2 == 0
                distance2 = (x-a(1)).^2 + (y-a(2)).^2;
            else
                u = min(1, max(0, ((x-a(1))*delta(1) + (y-a(2))*delta(2)) / length2));
                distance2 = (x-a(1)-u*delta(1)).^2 + (y-a(2)-u*delta(2)).^2;
            end
            min_d2 = min(min_d2, distance2);
            j = i;
        end
        inside(pending) = hit | min_d2 <= tolerance_m^2;
    end
    inside = reshape(inside, original_size);
end
