import sys
import unittest
sys.dont_write_bytecode = True
import analyze_sensitivity as analysis


class AnalysisTests(unittest.TestCase):
    def test_full_design_counts_are_108_density_pairs_and_72_tolerance_pairs(self):
        counts = analysis.expected_counts(analysis.run.read_json(analysis.run.PROTOCOL))
        self.assertEqual(counts, {'new_prediction_jobs': 36, 'reference_jobs': 18,
                                 'summary_rows': 216, 'density_pairs': 108, 'tolerance_pairs': 72})

    def test_full_cartesian_density_pair_generation_matches_design(self):
        p = analysis.run.read_json(analysis.run.PROTOCOL)
        rows = []
        for case in p['cases']:
            for core in p['core_configs']:
                for condition in p['conditions']:
                    for tolerance in p['contact_tolerances_m']:
                        for variant in p['variants']:
                            for count in p['density_counts']:
                                rows.append({'case_id': case, 'core_id': core['id'], 'condition': condition,
                                             'contact_tolerance_m': tolerance, 'margin_m': variant['margin'],
                                             'confirmation_s': variant['confirmation'], 'target_count': count,
                                             'right_pct': .01, 'negative_fp_pct': 1.,
                                             'common_2s_reference_fpr_pct': .1, 'right_lead_p10_s': 1.5})
        pairs = analysis.run.density_pairs(rows)
        self.assertEqual(len(rows), 216)
        self.assertEqual(len(pairs), 108)
        self.assertTrue(all(r['right_pct_paired_effect_change_pp'] == 0 for r in pairs))


if __name__ == '__main__':
    unittest.main()
