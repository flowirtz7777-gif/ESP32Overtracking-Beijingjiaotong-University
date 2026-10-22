import itertools
import unittest

from joint_effects import LEVELS, METRICS, pair_tables


def block():
    result = []
    for w, m, c in itertools.product(*LEVELS):
        value = 5-w+2*m+c+3*w*m+4*w*c+7*m*c+8*w*m*c
        row = {'partition': 'test', 'case_id': 'case', 'config_id': 'method', 'condition': 'clean',
               'preprocessing': 'raw', 'job_id': 'job', 'EXIT_W_s': w, 'margin_m': m,
               'confirmation_s': c, 'target_count': 70000, 'score_end_s': 30,
               'right_contacts': 10000, 'exit_right_contacts': 100}
        row.update({metric: value for metric in METRICS})
        result.append(row)
    return result


class PairTests(unittest.TestCase):
    def test_complete_counts(self):
        windows, processing, interactions = pair_tables(block())
        self.assertEqual((len(windows), len(processing), len(interactions)), (6, 14, 13))

    def test_window_change_keeps_other_factors_fixed(self):
        windows, _, _ = pair_tables(block())
        row = next(row for row in windows if row['margin_m'] == .02 and row['confirmation_s'] == .1)
        self.assertAlmostEqual(row['right_pct_delta_pp'], -1+3*.02+4*.1+8*.02*.1)

    def test_triple_interaction(self):
        _, _, interactions = pair_tables(block())
        row = next(row for row in interactions if row['interaction'] == 'window_margin_confirmation'
                   and row['high_margin_m'] == .02)
        self.assertAlmostEqual(row['right_pct_delta_pp'], 8*.02*.1)

    def test_incomplete_and_duplicate_rejected(self):
        with self.assertRaises(AssertionError):
            pair_tables(block()[:-1])
        with self.assertRaises(AssertionError):
            pair_tables(block() + block()[:1])

    def test_missing_exit_contacts_remain_missing(self):
        rows = block()
        for row in rows:
            row['exit_right_contacts'] = 0
            row['exit_right_pct'] = None
        windows, _, interactions = pair_tables(rows)
        self.assertIsNone(windows[0]['exit_right_pct_delta_pp'])
        self.assertIsNone(interactions[0]['exit_right_pct_delta_pp'])

    def test_mismatched_scoring_period_rejected(self):
        rows = block()
        rows[0]['score_end_s'] = 31
        with self.assertRaises(AssertionError):
            pair_tables(rows)


if __name__ == '__main__':
    unittest.main()
