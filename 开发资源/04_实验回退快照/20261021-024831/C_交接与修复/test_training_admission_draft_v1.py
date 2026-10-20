import copy
import unittest
import training_admission_draft_v1 as c


def fixture():
    m={k:True for k in c.GATES}; m.update({k:'a'*64 for k in c.HASHES})
    m.update(counts=dict(raw_rows=4,eligible_training_rows=2,unknown_rows_retained=1,
        outside_domain_rows_retained=1,unknown_or_conflicted_training_rows=0),
        features=['speed_mps','alpha_gain'],preregistered_features=['speed_mps','alpha_gain'])
    rows=[dict(row_id='a',group='g1',lineage='l1',partition='train',target_known=True),
        dict(row_id='b',group='g2',lineage='l2',partition='validation',target_known=True)]
    return m,rows


class AdmissionTests(unittest.TestCase):
    def test_complete_synthetic_manifest(self):
        m,rows=fixture(); self.assertEqual(c.validate(m,rows)['groups'],2)

    def test_each_missing_or_truthy_unpassed_gate_rejected(self):
        for key in c.GATES:
            for value in (False,None,1,'true'):
                m,rows=fixture(); m[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError): c.validate(m,rows)

    def test_missing_or_malformed_evidence_hash_rejected(self):
        for key in c.HASHES:
            m,rows=fixture(); m[key]='a'*63
            with self.subTest(key=key),self.assertRaises(ValueError): c.validate(m,rows)

    def test_original_unknown_rows_not_silently_dropped(self):
        m,rows=fixture(); m['counts']['unknown_rows_retained']=0
        with self.assertRaises(ValueError): c.validate(m,rows)

    def test_unknown_target_never_negative(self):
        m,rows=fixture(); m['counts']['unknown_or_conflicted_training_rows']=1
        with self.assertRaises(ValueError): c.validate(m,rows)

    def test_same_trajectory_not_split(self):
        m,rows=fixture(); rows[1]['group']='g1'
        with self.assertRaises(ValueError): c.validate(m,rows)

    def test_density_noise_same_lineage_not_split(self):
        m,rows=fixture(); rows[1]['lineage']='l1'
        with self.assertRaises(ValueError): c.validate(m,rows)

    def test_final_test_never_enters_training(self):
        m,rows=fixture(); rows[1]['partition']='final_test'
        with self.assertRaises(ValueError): c.validate(m,rows)

    def test_each_forbidden_feature_rejected(self):
        for key in c.FORBIDDEN|{'future_action','truth_edge','score_rank'}:
            m,rows=fixture(); m['features']=m['preregistered_features']=[key]
            with self.subTest(key=key),self.assertRaises(ValueError): c.validate(m,rows)

    def test_unregistered_or_duplicate_feature_rejected(self):
        for values in (['speed_mps'],['speed_mps','speed_mps']):
            m,rows=fixture(); m['features']=values
            with self.subTest(values=values),self.assertRaises(ValueError): c.validate(m,rows)

    def test_missing_duplicate_or_unknown_training_row_rejected(self):
        for kind in range(3):
            m,rows=fixture()
            if kind==0: rows.pop()
            elif kind==1: rows[1]['row_id']='a'
            else: rows[1]['target_known']=False
            with self.subTest(kind=kind),self.assertRaises(ValueError): c.validate(m,rows)

    def test_no_held_out_group_rejected(self):
        m,rows=fixture(); rows[1]['partition']='train'
        with self.assertRaises(ValueError): c.validate(m,rows)


if __name__=='__main__': unittest.main(verbosity=2)
