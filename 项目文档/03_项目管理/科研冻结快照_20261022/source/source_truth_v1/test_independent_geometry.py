import importlib.util
import itertools
import unittest
from fractions import Fraction as F
from pathlib import Path

from . import independent_geometry as G
STEP = G._STEP


def trig_interval(x, cosine=False):
    lo, hi = STEP.scalar_trig(F(x), cosine)
    return G._inflate((lo, lo), hi)


def exact_pose(point, center, rows, t, delta, lh):
    x = [F(center[k]) + STEP.at(G._poly(rows[k]), F(t)) + F(delta[k]) for k in range(4)]
    psi = x[2]-x[3]
    A, B = F(point[0])-x[0], F(point[1])-x[1]
    cpsi, spsi = trig_interval(psi, True), trig_interval(psi)
    cphi, sphi = trig_interval(x[3], True), trig_interval(x[3])
    q = G._sub(G._add(G._mul((A,A),cpsi),G._mul((B,B),spsi)),G._mul((F(lh),F(lh)),cphi))
    r = G._add(G._sub(G._mul((A,A),spsi),G._mul((B,B),cpsi)),G._mul((F(lh),F(lh)),sphi))
    return q, r


def segment_dist2(p, a, b):
    vx, vy = b[0]-a[0], b[1]-a[1]
    den = vx*vx+vy*vy
    u = max(F(0), min(F(1), ((p[0]-a[0])*vx+(p[1]-a[1])*vy)/den))
    dx, dy = p[0]-(a[0]+u*vx), p[1]-(a[1]+u*vy)
    return dx*dx+dy*dy


def rectangle_edges(q, r, length, half):
    vertices = [(0,-half),(-length,-half),(-length,half),(0,half)]
    distances=tuple(segment_dist2((q,r),vertices[i],vertices[(i+1)%4]) for i in range(4))
    return distances[3], distances[2], distances[1], distances[0]


class IndependentFiniteRectangleTests(unittest.TestCase):
    def test_correlated_polynomial_with_nonzero_tube_corners(self):
        n, h = 5, F(1,4)
        center = [F(1,3),F(-2,5),F(1,2),F(1,10)]
        rows = [[F(0)]*(n+1) for _ in range(4)]
        rows[0][1], rows[0][3] = F(1,5), F(-1,7)
        rows[1][1], rows[1][2] = F(-1,6), F(1,9)
        rows[2][1], rows[2][2] = F(1,4), F(-1,8)
        rows[3][1], rows[3][3] = F(-1,10), F(1,13)
        errors = [F(1,10**8),F(2,10**8),F(3,10**9),F(4,10**9)]
        cell = (F(1,16),F(1,8)); point = (F(4),F(-3)); lh=F(9,5)
        out = G.project(point,center,rows,cell,h,n,errors,lh,F(27,2),F(2))
        self.assertEqual(out["input_state_errors"],tuple(errors))
        self.assertFalse(out["tube_reset"])
        self.assertEqual(len(out["finite_edge_distance_squared"]),4)
        for t in (cell[0],sum(cell)/2,cell[1]):
            for signs in itertools.product((-1,1),repeat=4):
                delta=[s*e for s,e in zip(signs,errors)]
                q,r=exact_pose(point,center,rows,t,delta,lh)
                self.assertLessEqual(out["q"][0],q[0]); self.assertLessEqual(q[1],out["q"][1])
                self.assertLessEqual(out["r"][0],r[0]); self.assertLessEqual(r[1],out["r"][1])

    def test_shifted_cell_range_is_tighter_than_full_step(self):
        n,h=4,F(1)
        center=[F(0)]*4; rows=[[F(0)]*(n+1) for _ in range(4)]
        rows[0][1]=F(1)
        wide=G.project((3,1),center,rows,(0,h),h,n,[0]*4,0,2,2)
        narrow=G.project((3,1),center,rows,(F(1,2),F(3,4)),h,n,[0]*4,0,2,2)
        self.assertLessEqual(narrow["q"][1]-narrow["q"][0],wide["q"][1]-wide["q"][0])
        self.assertEqual(narrow["trig_anchor"],"original_step_zero_origin_full_polynomial")

    def test_rectangle_interior_each_face_and_corner_and_edge_bounds(self):
        n,h=3,F(1,5);center=[F(0)]*4;rows=[[F(0)]*(n+1) for _ in range(4)]
        def calc(p): return G.project(p,center,rows,(0,h),h,n,[0]*4,0,4,2)
        for p in ((-2,0),(0,0),(-4,0),(-2,1),(-2,-1)):
            self.assertEqual(calc(p)["distance_squared"],(0,0))
        for p in ((1,0),(-5,0),(-2,2)):
            out=calc(p)
            self.assertGreater(out["distance_squared"][0],0)
            want=rectangle_edges(F(p[0]),-F(p[1]),F(4),F(1))
            bounds=out["finite_edge_distance_squared"]
            self.assertEqual(sorted((lo for lo,hi in bounds)),sorted(want))
            self.assertTrue(all(lo==hi for lo,hi in bounds))
        for q,r in ((F(1),F(0)),(F(-5),F(0)),(F(-2),F(2)),(F(-2),F(0))):
            got=calc((q,r))["finite_edge_distance_squared"]
            want=rectangle_edges(q,-r,F(4),F(1))
            for bound, exact in zip(got,want): self.assertLessEqual(bound[0],exact); self.assertLessEqual(exact,bound[1])

    def test_rejects_bad_types_shapes_cells_and_dimensions(self):
        n,h=2,F(1,4); c=[0]*4; rows=[[0]*(n+1) for _ in range(4)]; e=[0]*4
        base=((1,1),c,rows,(0,h),h,n,e,1,4,2)
        bad=[(1.0,1),c,rows,(0,h),h,n,e,1,4,2]
        with self.assertRaises(TypeError):G.project(*bad)
        with self.assertRaises(ValueError):G.project((0,0),c,rows,(-1,h),h,n,e,1,4,2)
        with self.assertRaises(ValueError):G.project((0,0),c,rows,(0,h),h,n,[-1,0,0,0],1,4,2)
        with self.assertRaises(ValueError):G.project((0,0),c,rows,(0,h),h,n,e,1,0,2)
        with self.assertRaises(ValueError):G.project((0,0),c,[[0,0]]*4,(0,h),h,n,e,1,4,2)


if __name__ == "__main__":
    unittest.main()
