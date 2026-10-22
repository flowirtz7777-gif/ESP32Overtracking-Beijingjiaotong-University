import unittest
from fractions import Fraction as F
from .primary.source_projection import compile_step,evaluate_cell,centered_range
class SourceProjectionTests(unittest.TestCase):
    def make(self,E=(0,0,0,0)):
        return compile_step((-3,0),(0,0,0,0),[[0]*7 for _ in range(4)],6,F(1,5),E,2,10,2)
    def test_fixed_full_tube_survives_cell_restriction(self):
        E=(F(1,10**7),F(2,10**7),F(3,10**8),F(4,10**8))
        c=self.make(E)
        a=evaluate_cell(c,0,F(1,10));b=evaluate_cell(c,F(1,10),F(1,5))
        self.assertEqual(a["source_full_step_errors"],E)
        self.assertEqual(b["source_full_step_errors"],E)
        self.assertEqual(a["source_trig_and_tube_domain"],(0,F(1,5)))
        self.assertFalse(a["scientific_admission_allowed"])
    def test_shifted_polynomial_bounds_not_point_samples(self):
        # (u-1)^2 in [9/10,11/10]: exact shift gives [0,1/100].
        lo,hi=centered_range((1,-2,1),F(9,10),F(11,10))
        self.assertEqual(hi,F(1,100));self.assertLessEqual(lo,0)
    def test_finite_front_rear_and_side(self):
        for point in ((3,0),(-9,0),(2,-2)):
            c=compile_step(point,(0,0,0,0),[[0]*7 for _ in range(4)],6,F(1,5),(0,0,0,0),2,10,2)
            out=evaluate_cell(c,0,F(1,5))
            self.assertLessEqual(out["distance_squared"][0],1)
            self.assertGreaterEqual(out["distance_squared"][1],1)
    def test_nonzero_dense_polynomial_coefficients_and_original_edge_order(self):
        P=[[0]*7 for _ in range(4)];P[0][1]=1
        c=compile_step((3,0),(0,0,0,0),P,6,F(1,5),(0,0,0,0),2,10,2)
        self.assertEqual(c["q"][0],F(1));self.assertEqual(c["q"][1],F(-1))
        out=evaluate_cell(c,F(1,10),F(1,5))
        self.assertEqual(out["q"],(F(4,5),F(9,10)))
        self.assertEqual(out["finite_edge_order"],("front","right","rear","left"))
        self.assertEqual(len(out["finite_edge_distance_squared"]),4)
    def test_invalid_shape_scalar_and_cell(self):
        with self.assertRaises(ValueError):self.make((0,-1,0,0))
        with self.assertRaises(ValueError):self.make((0,0,0,True))
        with self.assertRaises(ValueError):evaluate_cell(self.make(),0,1)
        with self.assertRaises(ValueError):compile_step((0,0),(0,0,0,0),[[0]*7]*4,True,1,(0,0,0,0),2,10,2)
if __name__=="__main__":unittest.main()
