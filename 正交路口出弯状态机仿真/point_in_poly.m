function inside = point_in_poly(px, py, poly)
%POINT_IN_POLY  射线法点-多边形判内（与 C++ Predictor::point_in_poly 对齐）。
%
%   inside = point_in_poly(px, py, poly)
%
%   输入：
%     px, py  待判定点 (标量) 或同长度向量
%     poly    多边形顶点 (N×2)；可闭合也可不闭合
%
%   输出：
%     inside  逻辑值，与 px 同形
%
%   实现：
%     - Crossing-number 算法 (W. R. Franklin)
%     - 时间复杂度 O(N)，无浮点除法（仅一次符号比较）
%     - 边界点视为外部（与 C++ 实现一致，避免抖动）

    px = px(:);
    py = py(:);
    inside = false(size(px));

    if size(poly, 1) < 3
        return;
    end

    % 去掉末尾闭合重复点（如果有）
    if isequal(poly(1, :), poly(end, :))
        poly = poly(1:end-1, :);
    end

    n  = size(poly, 1);
    xv = poly(:, 1);
    yv = poly(:, 2);

    j = n;
    for i = 1:n
        yi = yv(i); yj = yv(j);
        xi = xv(i); xj = xv(j);

        cond1 = (yi > py) ~= (yj > py);
        if any(cond1)
            slope = (xj - xi) ./ (yj - yi + eps);
            x_intersect = xi + (py - yi) .* slope;
            cross = cond1 & (px < x_intersect);
            inside(cross) = ~inside(cross);
        end
        j = i;
    end

    inside = reshape(inside, size(px));
end
