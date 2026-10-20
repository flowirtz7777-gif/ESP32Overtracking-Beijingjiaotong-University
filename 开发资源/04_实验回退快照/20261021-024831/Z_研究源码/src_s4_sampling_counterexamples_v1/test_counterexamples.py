import tempfile
from pathlib import Path
import unittest
from collect_counterexamples import miss_difference, base


class CounterexampleTests(unittest.TestCase):
    def test_new_and_disappeared_are_not_netted(self):
        row = miss_difference([1, 3], [3, 4])
        self.assertEqual(row['high_only_miss_indices'], [4])
        self.assertEqual(row['low_only_miss_indices'], [1])
        self.assertFalse(row['zero_miss_claim_lost'])

    def test_zero_claim_loss(self):
        row = miss_difference([], [7, 8, 7])
        self.assertTrue(row['zero_miss_claim_lost'])
        self.assertEqual(row['high_only_miss_indices'], [7, 8])

    def test_json_keeps_lists_losslessly(self):
        value = {'pairs': [miss_difference([], [7, 8])]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'indices.json'
            base.write_json_retry(path, value)
            self.assertEqual(base.read_json(path), value)


if __name__ == '__main__':
    unittest.main()
