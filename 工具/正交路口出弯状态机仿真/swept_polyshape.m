function [shape, lines] = swept_polyshape(poly)
%SWEPT_POLYSHAPE Union all filled pieces, retaining degenerate lines separately.
    shape = polyshape();
    lines = zeros(0, 2);
    shapes = polyshape.empty(0, 1);
    breaks = [0; find(any(~isfinite(poly), 2)); size(poly, 1) + 1];
    for k = 1:numel(breaks)-1
        piece = poly(breaks(k)+1:breaks(k+1)-1, :);
        if isempty(piece), continue; end
        points = unique(piece, 'rows');
        if size(points, 1) >= 3 && rank(points - points(1, :), 1e-12) >= 2
            if isequal(piece(1, :), piece(end, :)), piece(end, :) = []; end
            % Pieces are local convex hulls; do not reinterpret near-collinear vertices.
            shapes(end+1, 1) = polyshape(piece(:, 1), piece(:, 2), 'Simplify', false); %#ok<AGROW>
        else
            lines = [lines; piece; NaN NaN]; %#ok<AGROW>
        end
    end
    if ~isempty(shapes)
        shape = union(shapes);
    end
end
