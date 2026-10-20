import tempfile
from pathlib import Path
import unittest
import run_recovery as recovery

class RecoveryTests(unittest.TestCase):
    def test_distinct_run(self):
        self.assertNotEqual(recovery.RUN, recovery.ORIGINAL)
        self.assertEqual(recovery.r.RUN, recovery.RUN)

    def test_same_frozen_science(self):
        expected = recovery.r.read(recovery.ORIGINAL / "source_manifest.json")
        self.assertEqual(recovery.r.source_signature(), expected)

    def test_unique_nine_frozen_jobs(self):
        jobs = recovery.dep.old_matrix()
        self.assertEqual(len({j['id'] for j in jobs}), 9)

    def test_interrupted_four_unique_jobs(self):
        cp = recovery.r.read(recovery.ORIGINAL / "checkpoint.json")
        self.assertEqual(len(cp['completed']), 4)
        self.assertEqual(len(cp['geometry']), 12)
        self.assertEqual(len(set(j['id'] for j in recovery.dep.old_matrix()) - set(cp['completed'])), 5)

    def test_full_scandir_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'a').write_bytes(b'123')
            (folder / 'b').mkdir()
            (folder / 'b/c').write_bytes(b'12345')
            self.assertEqual(recovery.scan_size(folder), 8)

    def test_lossless_array_codec(self):
        import io
        import numpy as np
        values = np.array([float('nan'), 2., 3.])
        with np.load(io.BytesIO(recovery.dep.npz_blob({'a': values}))) as restored:
            np.testing.assert_array_equal(restored['a'], values)

if __name__ == '__main__':
    unittest.main()
