import unittest
import numpy as np
import edge_merge_core as c


def fixture():
    old=dict(contact_status=np.array([1,2,0,1,1],np.int8),
        contact_lower_s=np.array([-0.,0.,np.nan,.2,.4]),contact_upper_s=np.array([1.,np.nan,np.nan,.3,.6]),
        nominal_instantaneous_edge=np.array([2,0,0,1,1],np.int8),
        possible_edge_codes=np.array([255,255,0,1,255],np.uint16),edge_certain=np.array([0,0,0,1,0],bool),
        budget_exhausted=np.zeros(5,bool),matrix=np.arange(10,dtype=np.int32).reshape(5,2))
    scope=np.array([1,1,1,1,0],bool); ids=np.flatnonzero(scope)
    new={k:v[ids].copy() for k,v in old.items()}
    new['edge_certain'][0]=True; new['possible_edge_codes'][0]=2
    return old,ids,new,scope,np.array([1,0,0,0],bool)


class Tests(unittest.TestCase):
    def test_scalar_vector_all_bytes(self):
        args=fixture(); a=c.merge_path(*args); b=c.merge_path(*args,scalar=True)
        self.assertTrue(all(c.same(a[k],b[k]) for k in a))

    def test_all_endpoints_nan_signedzero_exact(self):
        args=fixture(); out=c.merge_path(*args)
        for key in set(out)-c.MUTABLE: self.assertTrue(c.same(out[key],args[0][key]))
        self.assertEqual(out['contact_lower_s'].view(np.uint64)[0],1<<63)

    def test_every_unselected_or_uncertified_row_exact(self):
        args=fixture(); out=c.merge_path(*args)
        for key in out: self.assertTrue(c.same(out[key][1:],args[0][key][1:]))

    def test_unknown_noncontact_and_already_certain_ineligible(self):
        for i in (1,2,3):
            args=list(fixture()); args[4][i]=True
            with self.subTest(i=i),self.assertRaises(ValueError): c.merge_path(*args)

    def test_endpoint_status_nominal_and_matrix_changes_rejected(self):
        for key in ('contact_lower_s','contact_upper_s','contact_status','nominal_instantaneous_edge','matrix'):
            args=list(fixture()); args[2][key][0]+=1
            with self.subTest(key=key),self.assertRaises(ValueError): c.merge_path(*args)

    def test_incorrect_singleton_or_missing_certainty_rejected(self):
        for key,value in (('possible_edge_codes',1),('possible_edge_codes',3),('edge_certain',False)):
            args=list(fixture()); args[2][key][0]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): c.merge_path(*args)

    def test_unsigned_duplicate_omitted_reordered_indices_rejected(self):
        for ids in (np.array([0,1,2,3],np.uint32),np.array([0,1,1,3]),np.array([0]),np.array([3,2,1,0])):
            args=list(fixture()); args[1]=ids
            with self.subTest(ids=ids),self.assertRaises(ValueError): c.merge_path(*args)

    def test_int32_supported(self):
        args=list(fixture()); args[1]=args[1].astype(np.int32)
        self.assertTrue(c.merge_path(*args)['edge_certain'][0])

    def test_full_field_shape_and_dtype_rejected(self):
        for value in (np.zeros(4,np.float32),np.zeros((4,1),np.float64)):
            args=list(fixture()); args[2]['contact_upper_s']=value
            with self.assertRaises(ValueError): c.merge_path(*args)

    def test_no_certificate_exact_reuse(self):
        old,ids,_,scope,_=fixture()
        out=c.merge_path(old,ids,{k:v[ids] for k,v in old.items()},scope,np.zeros(len(ids),bool))
        self.assertTrue(all(c.same(old[k],out[k]) for k in old))

    def test_empty_scope_and_no_point_queries(self):
        old,*_=fixture(); ids=np.array([],np.int64)
        out=c.merge_path(old,ids,{k:v[:0] for k,v in old.items()},np.zeros(5,bool),np.zeros(0,bool),scalar=True)
        self.assertTrue(all(c.same(old[k],out[k]) for k in old))

    def test_all_parent_provenance_including_suffix_exact_separate_new_masks(self):
        args=fixture(); old,ids,_,scope,proof=args
        xy=np.arange(10,dtype=float).reshape(5,2)
        original={'xy':xy}
        for tag in c.TAGS:
            original.update({tag+'__'+k:v for k,v in old.items()})
            for prefix in ('merge','upper_merge','local_motion','probe_merge','suffix_merge'):
                original[prefix+'_changed_'+tag+'__packbits']=np.array([4],np.uint8)
        paths={tag:c.merge_path(*args) for tag in c.TAGS}
        group=c.group_payload(original,paths,paths['oldpath'],np.arange(5,dtype=np.uint16),scope,
            {tag:ids for tag in c.TAGS},{tag:proof for tag in c.TAGS})
        for name,value in original.items():
            if name.endswith('__packbits'): self.assertTrue(c.same(value,group[name]))
        self.assertEqual(c.unpack(group['edge_cover_merge_certified_oldpath__packbits'],5).tolist(),[1,0,0,0,0])

    def test_original_projection_duplicate_int32_and_padding(self):
        args=fixture(); old=args[0]; xy=np.arange(10,dtype=float).reshape(5,2)
        group={'suffix_merge_changed_oldpath__packbits':np.array([4],np.uint8),
            'edge_cover_merge_certified_oldpath__packbits':np.array([1],np.uint8)}
        for ids in (np.array([4,0,4,1,0],np.int32),np.array([],np.int64)):
            params=(ids,xy,xy[ids],{tag:old for tag in c.TAGS},old,np.zeros(5,np.uint16),args[3],group)
            a=c.project(*params); b=c.project(*params,scalar=True)
            self.assertTrue(all(c.same(a[k],b[k]) for k in a)); self.assertTrue(c.same(a['union_index'],ids))
            for name,mask in a.items():
                if name.endswith('__packbits'): self.assertFalse(np.unpackbits(mask,bitorder='little')[len(ids):].any())

    def test_all_possible_fields_required(self):
        args=list(fixture()); del args[2]['matrix']
        with self.assertRaises(ValueError): c.merge_path(*args)


if __name__=='__main__': unittest.main()
