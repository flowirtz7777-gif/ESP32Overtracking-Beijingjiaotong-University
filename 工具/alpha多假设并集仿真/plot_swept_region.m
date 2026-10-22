function h = plot_swept_region(poly, color, varargin)
%PLOT_SWEPT_REGION Draw the same union used for area and point queries.
    [shape, lines] = swept_polyshape(poly);
    h = [];
    if shape.NumRegions > 0
        h = plot(shape, 'FaceColor', color, varargin{:});
    end
    if ~isempty(lines)
        was_held = ishold;
        hold on;
        line_handle = plot(lines(:, 1), lines(:, 2), '-', 'Color', color);
        if isempty(h)
            h = line_handle;
        else
            set(line_handle, 'HandleVisibility', 'off');
        end
        if ~was_held, hold off; end
    end
    if isempty(h)
        h = plot(NaN, NaN, '-', 'Color', color);
    end
end
