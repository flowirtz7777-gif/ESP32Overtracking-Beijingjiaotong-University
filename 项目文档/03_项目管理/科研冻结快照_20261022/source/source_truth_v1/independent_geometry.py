"""Independent sparse-rational finite-rectangle geometry candidate.

Pure synthetic/math code only. It does not assign labels or admit a source
trajectory. Inputs are exact rationals, a full original-step polynomial, and
the caller's already-certified all-time state tube.
"""
from fractions import Fraction as F
from math import comb
import importlib.util
from .independent_math import independent_step_verifier as _STEP

def _q(x):
    if isinstance(x, bool) or not isinstance(x, (int, F)):
        raise TypeError("Only exact int/Fraction inputs are accepted")
    return F(x)


def _interval(x):
    if not isinstance(x, (tuple, list)) or len(x) != 2:
        raise TypeError("An interval must be a two-element tuple/list")
    lo, hi = map(_q, x)
    if lo > hi:
        raise ValueError("Reversed interval")
    return lo, hi


def _add(a, b):
    a, b = _interval(a), _interval(b)
    return a[0] + b[0], a[1] + b[1]


def _neg(a):
    a = _interval(a)
    return -a[1], -a[0]


def _sub(a, b):
    return _add(a, _neg(b))


def _mul(a, b):
    a, b = _interval(a), _interval(b)
    v = [x*y for x in a for y in b]
    return min(v), max(v)


def _square(a):
    a = _interval(a)
    return (F(0) if a[0] <= 0 <= a[1] else min(a[0]**2, a[1]**2),
            max(a[0]**2, a[1]**2))


def _inflate(a, e):
    a, e = _interval(a), _q(e)
    if e < 0:
        raise ValueError("Error radius must be nonnegative")
    return a[0]-e, a[1]+e


def _poly(row):
    if not isinstance(row, (tuple, list)) or not row:
        raise TypeError("Polynomial row must be a nonempty coefficient sequence")
    return {k: _q(v) for k, v in enumerate(row) if _q(v)}


def _padd(a, b):
    return _STEP.plus(a, b)


def _pscale(a, x):
    return _STEP.scaled(a, _q(x))


def _psub(a, b):
    return _STEP.minus(a, b)


def _pmul(a, b):
    return _STEP.product(a, b)


def _pweight(a, h):
    return _STEP.weight(a, h)


def _shifted_range(p, a, b):
    """Exact binomial shift to cell midpoint, then interval Horner on [-d,d]."""
    mid, rad = (a+b)/2, (b-a)/2
    degree = max(p, default=0)
    shifted = {}
    for j in range(degree+1):
        shifted[j] = sum((v*comb(k, j)*mid**(k-j)
                          for k, v in p.items() if k >= j), F(0))
    out = (shifted[degree], shifted[degree])
    for j in range(degree-1, -1, -1):
        out = _add(_mul(out, (-rad, rad)), (shifted[j], shifted[j]))
    return out


def _absmax(a):
    a = _interval(a)
    return max(abs(a[0]), abs(a[1]))


def _positive_part(a):
    a = _interval(a)
    return max(F(0), a[0]), max(F(0), a[1])


def _abs_interval(a):
    a = _interval(a)
    return (F(0) if a[0] <= 0 <= a[1] else min(abs(a[0]), abs(a[1])),
            max(abs(a[0]), abs(a[1])))


def _max_interval(a, b):
    a, b = _interval(a), _interval(b)
    return max(a[0], b[0]), max(a[1], b[1])


def _distance_to_rectangle(q, r, length, half_width):
    along = _max_interval(_positive_part(q), _positive_part(_neg(_add((length, length), q))))
    across = _positive_part(_sub(_abs_interval(r), (half_width, half_width)))
    return _add(_square(along), _square(across))


def _edge_distances(q, r, length, half_width):
    """Bounds in contact_primitives order: front, right, rear, left."""
    outside_r = _positive_part(_sub(_abs_interval(r), (half_width, half_width)))
    outside_q = _positive_part(_sub(_abs_interval(_add(q, (length/2, length/2))),
                                    (length/2, length/2)))
    return (
        _add(_square(q), _square(outside_r)),
        _add(_square(_sub(r, (half_width, half_width))), _square(outside_q)),
        _add(_square(_add(q, (length, length))), _square(outside_r)),
        _add(_square(_add(r, (half_width, half_width))), _square(outside_q)),
    )


def project(point, center, rows, cell, original_step, degree, state_errors,
            hitch_offset, trailer_length, width):
    """Enclose q/r and finite-rectangle distance on a cell of one original step.

    `rows` are full zero-origin deviations for [xB,yB,theta,phi]. `state_errors`
    are the caller's all-time bounds on that same original step. Cell restriction
    changes polynomial range evaluation only: trig series and errors stay anchored
    to the original step and the supplied tube is never reset.
    """
    n = degree
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise TypeError("degree must be a nonnegative integer")
    if not isinstance(point, (tuple, list)) or len(point) != 2:
        raise TypeError("point must contain exactly two coordinates")
    if not isinstance(center, (tuple, list)) or len(center) != 4:
        raise TypeError("center must contain exactly four states")
    if not isinstance(rows, (tuple, list)) or len(rows) != 4:
        raise TypeError("rows must contain exactly four polynomials")
    if not isinstance(state_errors, (tuple, list)) or len(state_errors) != 4:
        raise TypeError("state_errors must contain exactly four radii")
    if not isinstance(cell, (tuple, list)) or len(cell) != 2:
        raise TypeError("cell must contain exactly two endpoints")

    point, center = list(map(_q, point)), list(map(_q, center))
    h = _q(original_step)
    a, b = map(_q, cell)
    lh, length, width = map(_q, (hitch_offset, trailer_length, width))
    err = list(map(_q, state_errors))
    P = [_poly(row) for row in rows]
    if h <= 0 or not (0 <= a < b <= h):
        raise ValueError("Cell must be nonempty and inside the original step")
    if length <= 0 or width <= 0 or lh < 0 or any(e < 0 for e in err):
        raise ValueError("Invalid dimensions or negative state error")
    for row in rows:
        if len(row) != n+1 or _q(row[0]) != 0:
            raise ValueError("Each state polynomial must have full degree shape and zero origin")

    theta, phi = center[2], center[3]
    Ppsi = _psub(P[2], P[3])
    spsi, espsi = _STEP.trig_offset(theta-phi, Ppsi, n, h)
    cpsi, ecpsi = _STEP.trig_offset(theta-phi, Ppsi, n, h, True)
    sphi, esphi = _STEP.trig_offset(phi, P[3], n, h)
    cphi, ecphi = _STEP.trig_offset(phi, P[3], n, h, True)

    A = _psub({0: point[0]-center[0]}, P[0])
    B = _psub({0: point[1]-center[1]}, P[1])
    qpoly = _psub(_padd(_pmul(A, cpsi), _pmul(B, spsi)), _pscale(cphi, lh))
    rpoly = _padd(_psub(_pmul(A, spsi), _pmul(B, cpsi)), _pscale(sphi, lh))

    # Trig truncation/series error, then the full caller-supplied state tube.
    na, nb = _pweight(A, h), _pweight(B, h)
    trig_q = na*ecpsi + nb*espsi + lh*ecphi
    trig_r = na*espsi + nb*ecpsi + lh*esphi
    ex, ey, et, ep = err
    # |sin|,|cos| <= 1 in the exact geometry; A/B magnitudes include nominal
    # movement over the entire original step. This Lipschitz allowance covers
    # both position perturbations and theta/phi perturbations jointly.
    geometry_lip = ex + ey + (na+nb+ex+ey)*(et+ep) + lh*ep
    qerr, rerr = trig_q+geometry_lip, trig_r+geometry_lip
    qbox = _inflate(_shifted_range(qpoly, a, b), qerr)
    rbox = _inflate(_shifted_range(rpoly, a, b), rerr)
    half = width/2
    d2 = _distance_to_rectangle(qbox, rbox, length, half)
    edges = _edge_distances(qbox, rbox, length, half)
    return {
        "q": qbox, "r": rbox,
        "distance_squared": d2,
        "finite_edge_distance_squared": edges,
        "nominal_polynomials": {"q": qpoly, "r": rpoly},
        "trig_error": {"q": trig_q, "r": trig_r},
        "state_error_lipschitz": geometry_lip,
        "coordinate_error": {"q": qerr, "r": rerr},
        "input_state_errors": tuple(err), "original_step": h,
        "cell": (a, b), "degree": n,
        "trig_anchor": "original_step_zero_origin_full_polynomial",
        "tube_reset": False, "label_or_admission": False,
    }
