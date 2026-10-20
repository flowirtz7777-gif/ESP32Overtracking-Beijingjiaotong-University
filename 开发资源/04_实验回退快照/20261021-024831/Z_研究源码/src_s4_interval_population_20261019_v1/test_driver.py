import unittest
import numpy as np
from run_population import npz_bytes,array_meta,old_discrepancies,validate_path,common
from population import label_population
import io


class DriverContractTests(unittest.TestCase):
    def test_lossless_nan_and_empty_arrays(self):
        arrays={'empty':np.empty((0,2)), 'time':np.array([np.nan,1.]),'bits':np.array([255],np.uint16)}
        blob=npz_bytes(arrays)
        with np.load(io.BytesIO(blob),allow_pickle=False) as z:
            self.assertEqual(array_meta({k:z[k] for k in z.files}),array_meta(arrays))

    def test_unknown_is_not_labeled_old_existence_error(self):
        target={'contact_time':np.array([1.,1.,np.nan]),'edge':np.array([2,2,0],np.int8)}
        combined={'contact_status':np.array([2,0,1]),'contact_lower_s':np.array([0.,np.nan,1.]),
            'contact_upper_s':np.array([2.,np.nan,2.]),'possible_edge_codes':np.array([255,0,2],np.uint16),
            'model_conflict':np.zeros(3,bool)}
        mask=old_discrepancies(target,combined)
        np.testing.assert_array_equal(mask['old_existence_incompatible'],[False,True,True])
        np.testing.assert_array_equal(mask['all_undetermined'],[True,False,False])

    def test_full_GE0S_witness_and_noncontact_verification(self):
        vehicle=common.Vehicle(l_h=0,L=2,width=2)
        time=np.array([0.,1.])
        state=np.array([[0.,0.,0.,0.],[4.,0.,0.,0.]])
        xy=np.array([[1.,0.],[1.,3.],[-3.,0.]])
        arrays=label_population(xy,time,state,vehicle=vehicle)
        result=validate_path(xy,time,state,arrays,0.,vehicle)
        self.assertEqual(result['full_witnesses_GE0S_checked'],1)
        self.assertEqual(result['noncontact_points_checked'],2)

    def test_nonfinite_policy_rejected(self):
        with self.assertRaises(ValueError):
            label_population(np.array([[0.,0.]]),np.array([0.,1.]),np.zeros((2,4)),spatial_error_m=np.nan)


if __name__=='__main__':
    unittest.main()
