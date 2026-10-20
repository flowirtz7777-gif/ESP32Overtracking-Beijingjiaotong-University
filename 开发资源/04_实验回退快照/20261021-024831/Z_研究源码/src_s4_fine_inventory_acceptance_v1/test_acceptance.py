import copy
import hashlib
import unittest
import verify_inventory as a


class AcceptanceTests(unittest.TestCase):
    def fixture(self):
        p = a.base.read_json(a.inventory.PROTOCOL)
        coarse = a.base.read_json(a.ROOT / p['coarse_population_report'])['cases'][0]
        result = a.base.read_json(a.inventory.RUN / 'cases' / (coarse['case_id']+'.json'))
        return result, coarse

    def test_exact_measured_counts_and_quota(self):
        proof, coarse = self.fixture()
        self.assertEqual(a.validate_metadata(proof, coarse), 2453007)
        self.assertEqual(a.reservation(2453007), 272816885)

    def test_changed_chunk_hash_chain_rejected(self):
        proof, coarse = self.fixture()
        changed = copy.deepcopy(proof)
        changed['regenerable_chunk_proofs'][0]['positive_count'] += 1
        with self.assertRaises(AssertionError):
            a.validate_metadata(changed, coarse)

    def test_row_gap_rejected_even_with_recomputed_chain(self):
        proof, coarse = self.fixture()
        proof['regenerable_chunk_proofs'][1]['row_start'] += 1
        proof['chunk_proof_chain_sha256'] = hashlib.sha256(a.inventory.encode(proof['regenerable_chunk_proofs'])).hexdigest()
        with self.assertRaises(AssertionError):
            a.validate_metadata(proof, coarse)

    def test_coarse_phase_change_not_accepted(self):
        proof, coarse = self.fixture()
        proof['coarse_population_array_hashes']['xy'] = '0'*64
        with self.assertRaises(AssertionError):
            a.validate_metadata(proof, coarse)

    def test_unknown_or_noninteger_count_not_admitted(self):
        for value in (None, -1, True, 1.5):
            with self.assertRaises(ValueError):
                a.reservation(value)


if __name__ == '__main__':
    unittest.main()
