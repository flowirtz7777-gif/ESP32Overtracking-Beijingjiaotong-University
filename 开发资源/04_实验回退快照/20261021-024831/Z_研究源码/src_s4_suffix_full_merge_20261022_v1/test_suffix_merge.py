import unittest
import numpy as np
import suffix_merge_core as c


def fixture():
    labels = dict(contact_status=np.array([2, 2, 1, 0, 2], np.int8),
        contact_lower_s=np.array([-0., 0., .1, np.nan, .2]),
        contact_upper_s=np.array([np.nan, np.nan, .3, np.nan, np.nan]),
        nominal_instantaneous_edge=np.array([0, 0, 2, 0, 0], np.int8),
        possible_edge_codes=np.array([255, 255, 2, 0, 255], np.uint16),
        edge_certain=np.array([False, False, True, False, False]),
        budget_exhausted=np.zeros(5, bool), interval_evaluations=np.arange(5, dtype=np.int32),
        initial_tolerance_contact_possible=np.array([1, 1, 0, 0, 0], bool))
    mask = np.array([True, True, True, True, False])
    index = np.flatnonzero(mask)
    proposed = {k: v[index].copy() for k, v in labels.items()}
    proposed['contact_status'][0] = 1
    proposed['contact_upper_s'][0] = .2
    proposed['nominal_instantaneous_edge'][0] = 3
    proposed['possible_edge_codes'][0] = 4
    proposed['edge_certain'][0] = True
    found = np.array([True, False, False, False])
    return labels, index, proposed, mask, found


class MergeTests(unittest.TestCase):
    def test_vector_and_scalar_every_byte(self):
        args = fixture()
        a, b = c.merge_path(*args), c.merge_path(*args, scalar=True)
        self.assertTrue(all(c.same(a[k], b[k]) for k in a))

    def test_lower_signed_zero_and_non_scope_nan_unchanged(self):
        args = fixture()
        out = c.merge_path(*args)
        self.assertTrue(c.same(out['contact_lower_s'], args[0]['contact_lower_s']))
        self.assertEqual(int(out['contact_lower_s'].view(np.uint64)[0]), 1 << 63)

    def test_every_non_witness_row_exact(self):
        args = fixture()
        out = c.merge_path(*args)
        for key in out:
            self.assertTrue(c.same(out[key][1:], args[0][key][1:]))

    def test_no_witness_exact_reuse(self):
        old, ids, new, mask, found = fixture()
        new = {k: v[ids].copy() for k, v in old.items()}
        out = c.merge_path(old, ids, new, mask, np.zeros(len(ids), bool))
        self.assertTrue(all(c.same(v, old[k]) for k, v in out.items()))

    def test_immutable_fields_and_lower_guard(self):
        for field in ('contact_lower_s', 'interval_evaluations', 'initial_tolerance_contact_possible'):
            args = list(fixture())
            args[2][field][0] = (not args[2][field][0]) if args[2][field].dtype == np.bool_ else args[2][field][0] + 1
            with self.subTest(field=field), self.assertRaises(ValueError): c.merge_path(*args)

    def test_unwitnessed_must_remain_unknown(self):
        args = list(fixture()); args[2]['contact_status'][1] = 0
        with self.assertRaises(ValueError): c.merge_path(*args)

    def test_existing_witness_and_noncontact_cannot_be_selected(self):
        for i in (2, 3):
            args = list(fixture()); args[4][i] = True
            with self.subTest(i=i), self.assertRaises(ValueError): c.merge_path(*args)

    def test_missing_full_scope_rejected(self):
        args = list(fixture()); args[1] = args[1][:-1]
        with self.assertRaises(ValueError): c.merge_path(*args)

    def test_reordered_duplicate_unsigned_indices_rejected(self):
        for index in (np.array([1,0,2,3]), np.array([0,1,1,3]), np.arange(4, dtype=np.uint32)):
            args = list(fixture()); args[1] = index
            with self.subTest(index=index), self.assertRaises(ValueError): c.merge_path(*args)

    def test_int32_scope_supported(self):
        args = list(fixture()); args[1] = args[1].astype(np.int32)
        self.assertEqual(c.merge_path(*args)['contact_status'][0], 1)

    def test_missing_extra_fields_rejected(self):
        for extra in (False, True):
            args = list(fixture())
            if extra: args[2]['unrecognized'] = np.zeros(4)
            else: del args[2]['budget_exhausted']
            with self.subTest(extra=extra), self.assertRaises(ValueError): c.merge_path(*args)

    def test_dtype_and_shape_rejected(self):
        for value in (np.zeros(4, np.float32), np.zeros((4,1), np.float64)):
            args = list(fixture()); args[2]['contact_upper_s'] = value
            with self.subTest(shape=value.shape), self.assertRaises(ValueError): c.merge_path(*args)

    def test_invalid_new_witness_rejected(self):
        for field, value in (('contact_status',2), ('contact_upper_s',np.nan), ('contact_upper_s',-.1),
                             ('nominal_instantaneous_edge',0), ('possible_edge_codes',2)):
            args = list(fixture()); args[2][field][0] = value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError): c.merge_path(*args)

    def test_uncertain_multi_edge_witness_retained(self):
        args = list(fixture()); args[2]['edge_certain'][0] = False; args[2]['possible_edge_codes'][0] = 12
        out = c.merge_path(*args)
        self.assertFalse(out['edge_certain'][0]); self.assertEqual(out['possible_edge_codes'][0],12)

    def test_padding_shape_dtype(self):
        for mask in (np.array([255], np.uint8), np.array([0,0], np.uint8), np.array([0],np.int8)):
            with self.subTest(mask=mask), self.assertRaises(ValueError): c.unpack(mask,5)

    def test_empty_scope(self):
        old,*_ = fixture(); ids=np.array([],np.int64)
        out=c.merge_path(old,ids,{k:v[:0] for k,v in old.items()},np.zeros(5,bool),np.zeros(0,bool),scalar=True)
        self.assertTrue(all(c.same(old[k],v) for k,v in out.items()))

    def test_original_order_duplicates_int32_and_empty_projection(self):
        old,*_=fixture(); xy=np.arange(10,dtype=np.float64).reshape(5,2)
        for ids in (np.array([4,0,4,2],np.int32), np.array([],np.int64)):
            mask=np.array([1,0,1,0,1],bool)
            group={'local_motion_selected_oldpath__packbits':np.packbits(mask,bitorder='little'),
                   'probe_merge_changed_oldpath__packbits':np.packbits(mask,bitorder='little')}
            a=c.project(ids,xy,xy[ids],{'oldpath':old,'independent':old},old,np.arange(5,dtype=np.uint16),mask,group)
            b=c.project(ids,xy,xy[ids],{'oldpath':old,'independent':old},old,np.arange(5,dtype=np.uint16),mask,group,scalar=True)
            self.assertTrue(all(c.same(a[k],b[k]) for k in a)); self.assertTrue(c.same(a['union_index'],ids))

    def test_projection_invalid_indices_or_coordinate_bytes(self):
        old,*_=fixture(); xy=np.arange(10,dtype=np.float64).reshape(5,2)
        for ids in (np.array([-1]),np.array([5]),np.array([0],np.uint32)):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                c.project(ids,xy,xy[:1],{'oldpath':old,'independent':old},old,np.zeros(5,np.uint16),np.zeros(5,bool),{})
        with self.assertRaises(ValueError):
            c.project(np.array([0]),xy,np.array([[-0.,1.]]),{'oldpath':old,'independent':old},old,np.zeros(5,np.uint16),np.zeros(5,bool),{})

    def test_multidimensional_immutable_provenance(self):
        args=list(fixture()); args[0]['matrix']=np.arange(10,dtype=np.int16).reshape(5,2)
        args[2]['matrix']=args[0]['matrix'][args[1]].copy()
        out=c.merge_path(*args,scalar=True); self.assertTrue(c.same(out['matrix'],args[0]['matrix']))
        args[2]['matrix'][0,1]+=1
        with self.assertRaises(ValueError): c.merge_path(*args)

    def test_group_masks_old_provenance_exact_and_only_new_witness_changed(self):
        old,ids,new,mask,found=fixture(); paths={tag:c.merge_path(old,ids,new,mask,found) for tag in c.TAGS}
        original={'xy':np.arange(10,dtype=np.float64).reshape(5,2),
                  'local_motion_changed_oldpath__packbits':np.array([4],np.uint8),
                  'probe_merge_changed_oldpath__packbits':np.array([4],np.uint8)}
        for tag in c.TAGS: original.update({tag+'__'+k:v for k,v in old.items()})
        out=c.group_payload(original,paths,paths['oldpath'],np.zeros(5,np.uint16),np.zeros(5,bool),
                            {tag:ids for tag in c.TAGS},{tag:found for tag in c.TAGS})
        self.assertTrue(c.same(out['local_motion_changed_oldpath__packbits'],original['local_motion_changed_oldpath__packbits']))
        self.assertEqual(c.unpack(out['suffix_merge_changed_oldpath__packbits'],5).tolist(),[1,0,0,0,0])
        self.assertTrue(c.same(out['probe_merge_changed_oldpath__packbits'],original['probe_merge_changed_oldpath__packbits']))


if __name__ == '__main__': unittest.main()
