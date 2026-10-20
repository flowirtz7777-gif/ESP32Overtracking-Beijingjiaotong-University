import copy
import hashlib
import unittest
import remediation_scope_core as c
H='a'*64; X='b'*64


def registered():
    return dict(report=r'Z:\research\runs\fine\jobs\job\report.json',report_sha256=H,location='Z',run='fine',job_id='job',
        point_outputs={'packed_points.npz':H},input_hashes={'targets.npz':H},inherited_input_trace=[],
        matched_base_dataset_manifests=['base'],expanded_population_requires_full_relabel=True)


def report():
    return dict(output_sha256={'packed_points.npz':H},full_target_count=3000000,full_target_array_sha256={'xy':X},target_manifest_sha256=H)


class Tests(unittest.TestCase):
    def indices(self):
        return c.index_descriptors([c.descriptor('target',H,dict(full_target_array_sha256={'xy':X},full_target_count=3000000))])

    def test_complete_expanded_descriptor_link_without_truth_claim(self):
        a=c.record(0,registered(),report(),{'case_id':'case'},self.indices())
        self.assertTrue(a['expanded_full_coordinate_descriptor_link_resolved'])
        self.assertFalse(a['corrected_labels_accepted']); self.assertFalse(a['raw_online_predictions_reuse_proven'])

    def test_delta_coordinate_digest_does_not_certify_full_coordinates(self):
        idx=c.index_descriptors([c.descriptor('delta',H,dict(delta_array_sha256={'xy':X}))])
        a=c.record(0,registered(),report(),{},idx)
        self.assertFalse(a['expanded_full_coordinate_descriptor_link_resolved'])

    def test_missing_coordinate_digest_preserved_unresolved(self):
        r=report(); del r['full_target_array_sha256']
        a=c.record(0,registered(),r,{},self.indices())
        self.assertFalse(a['expanded_full_coordinate_descriptor_link_resolved'])

    def test_wrong_point_output_binding_stops(self):
        r=report(); r['output_sha256']['packed_points.npz']=X
        with self.assertRaises(ValueError): c.record(0,registered(),r,{},self.indices())

    def test_different_case_and_tolerance_not_silently_assumed_equal(self):
        a=c.record(0,registered(),report(),{'case_id':'first','contact_tolerance_m':.025},self.indices())
        b=c.record(1,registered(),report(),{'case_id':'second','contact_tolerance_m':.1},self.indices())
        self.assertNotEqual(a['configuration_case'],b['configuration_case'])
        self.assertNotEqual(a['configuration_contact_tolerance_m'],b['configuration_contact_tolerance_m'])

    def test_counts_are_records_not_independent_samples(self):
        rows=[c.record(i,registered(),report(),{},self.indices()) for i in range(3)]
        s=c.summarize(rows); self.assertEqual(s['output_file_records_not_experiments'],3)
        self.assertEqual(s['corrected_prediction_scores_accepted'],0)

    def test_duplicate_registry_index_rejected(self):
        a=c.record(0,registered(),report(),{},self.indices())
        with self.assertRaises(ValueError): c.summarize([a,a])

    def test_zero_counts_and_missing_configuration_fields_preserved(self):
        r=report(); r['full_target_count']=0
        a=c.record(0,registered(),r,{},self.indices())
        self.assertEqual(a['declared_target_count_not_array_verified'],0)
        self.assertIsNone(a['configuration_contact_tolerance_m'])

    def test_invalid_declared_count_rejected(self):
        for value in (-1,True,'3'):
            r=report(); r['full_target_count']=value
            with self.subTest(value=value),self.assertRaises(ValueError): c.record(0,registered(),r,{},self.indices())

    def test_all_exact_manifest_and_referenced_file_links_retained(self):
        d=c.descriptor('delta',X,dict(file_sha256=H))
        a=c.record(0,registered(),report(),{},c.index_descriptors([d,d]))
        self.assertEqual(len(a['descriptor_file_links']),2)

    def test_descriptor_preserves_all_field_names_and_declared_counts(self):
        a=c.descriptor('p',H,dict(unique_target_count=17,unexpected='retain key name'))
        self.assertIn('unexpected',a['field_names']); self.assertFalse(a['scientific_truth_accepted'])
        self.assertEqual(a['declared_counts_not_verified_array_lengths']['unique_target_count'],17)

    def test_bundle_exact_every_source_file(self):
        blobs={'src/a.py':b'print(1)\n','source/protocol.json':b'{"x":1}'}
        blob=c.source_bundle(blobs)
        c.verify_bundle(blob,{k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()})
        self.assertEqual(blob,c.source_bundle(blobs))

    def test_bundle_missing_extra_or_changed_source_rejected(self):
        blob=c.source_bundle({'a.py':b'1'})
        for sig in ({},{'a.py':H},{'a.py':hashlib.sha256(b'1').hexdigest(),'extra.py':H}):
            with self.assertRaises(ValueError): c.verify_bundle(blob,sig)

    def test_bundle_relative_paths_only(self):
        for name in ('../x','C:/x','/x'):
            with self.subTest(name=name),self.assertRaises(ValueError): c.source_bundle({name:b'x'})


if __name__=='__main__': unittest.main()
