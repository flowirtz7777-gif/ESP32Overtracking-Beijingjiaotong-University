import copy
import gzip
import io
import unittest
from unittest.mock import patch
import numpy as np
import resume_driver as d
import compact_io as s
from test_candidate import SparsePrefixTests


class LosslessContinuationTests(unittest.TestCase):
    def setUp(self):
        d.configure()
        self.arrays = {'float': np.array([np.nan, -0., np.inf]), 'index': np.array([0, 17, 29], np.int64),
                       'mask_packbits': np.packbits(np.array([True, False, True]), bitorder='little')}
        self.blob = d.base.npz_bytes(self.arrays)
        self.record = {'summary': {'points': 3, 'strict_prefix_gate_passed': False},
                       'rows': [{'all_required_prefix_excluded': False, 'status': 'unknown_time_leaf'}],
                       'arrays': d.base.array_meta(self.arrays), 'npz_sha256': d.r.sha(self.blob)}
        self.raw = d.r.encoded(self.record)

    def test_metadata_roundtrip_every_original_byte(self):
        stub, packed = s.encode_record(self.raw)
        raw, record = s.decode_record(stub, packed)
        self.assertEqual(raw, self.raw)
        self.assertEqual(record, self.record)

    def test_full_array_dtype_nan_and_padding_roundtrip(self):
        with np.load(io.BytesIO(self.blob), allow_pickle=False) as z:
            decoded = {k: z[k] for k in z.files}
        self.assertEqual(d.base.array_meta(decoded), d.base.array_meta(self.arrays))
        self.assertEqual(decoded['mask_packbits'][0], 5)

    def test_deterministic_gzip(self):
        self.assertEqual(s.encode_record(self.raw), s.encode_record(self.raw))

    def test_gzip_corruption_rejected(self):
        stub, packed = s.encode_record(self.raw)
        bad = packed[:-1] + bytes([packed[-1] ^ 1])
        with self.assertRaises(RuntimeError):
            s.decode_record(stub, bad)

    def test_decompressed_length_corruption_rejected(self):
        stub, packed = s.encode_record(self.raw)
        stub['metadata_bytes'] += 1
        with self.assertRaises(RuntimeError):
            s.decode_record(stub, packed)

    def test_original_metadata_signature_corruption_rejected(self):
        stub, packed = s.encode_record(self.raw)
        stub['metadata_sha256'] = '0' * 64
        with self.assertRaises(RuntimeError):
            s.decode_record(stub, packed)

    def test_extra_manifest_fields_rejected(self):
        stub, packed = s.encode_record(self.raw)
        stub['silently_dropped_nodes'] = True
        with self.assertRaises(RuntimeError):
            s.decode_record(stub, packed)

    def test_npz_body_manifest_mismatch_rejected(self):
        stub, packed = s.encode_record(self.raw)
        stub['npz_sha256'] = '0' * 64
        with self.assertRaises(RuntimeError):
            s.decode_record(stub, packed)

    def test_summary_cannot_clear_unknown(self):
        stub, packed = s.encode_record(self.raw)
        stub['summary']['strict_prefix_gate_passed'] = True
        with self.assertRaises(RuntimeError):
            s.decode_record(stub, packed)

    def test_repeated_tree_nodes_are_not_dropped(self):
        raw = d.r.encoded({**self.record, 'rows': self.record['rows'] * 10000})
        stub, packed = s.encode_record(raw)
        out, record = s.decode_record(stub, packed)
        self.assertEqual(raw, out)
        self.assertEqual(len(record['rows']), 10000)
        self.assertLess(len(packed), len(raw) / 10)

    def test_save_encoded_batches_only_verified_lossless_payloads(self):
        captured = []
        with patch.object(d.r, 'batch', side_effect=lambda x: captured.extend(x)), \
             patch.object(d.r, 'file_hash', return_value='new-stub-sha'):
            entry = s.save_encoded(d.RUN / 'synthetic', self.blob, self.raw)
        payload = {p.name: value for p, value in captured}
        self.assertEqual(payload['arrays.npz'], self.blob)
        self.assertEqual(gzip.decompress(payload['metadata.json.gz']), self.raw)
        self.assertEqual(entry['summary'], self.record['summary'])

    def test_save_rejects_wrong_npz_before_any_write(self):
        with patch.object(d.r, 'batch') as writes:
            with self.assertRaises(RuntimeError):
                s.save_encoded(d.RUN / 'synthetic', self.blob + b'x', self.raw)
        writes.assert_not_called()

    def test_same_frozen_path_code_object_and_local_namespace(self):
        original_globals_run = d.previous.run_path.__globals__['RUN']
        fn = d.bound_path_audit()
        self.assertIs(fn.__code__, d.previous.run_path.__code__)
        self.assertIs(fn.__globals__['base'].save_arrays, s.save_arrays)
        self.assertEqual(fn.__globals__['RUN'], d.RUN)
        self.assertEqual(d.previous.run_path.__globals__['RUN'], original_globals_run)

    def test_same_scientific_outputs_with_new_encoder_only(self):
        fn = d.bound_path_audit()
        saved = {}
        def capture(folder, arrays, record):
            saved.update(folder=folder, arrays=arrays, record=record)
            return {'summary': record['summary']}
        with patch.object(fn.__globals__['base'], 'save_arrays', side_effect=capture), \
             patch.object(d.r, 'file_hash', return_value='synthetic-source'):
            candidate = (np.array([[100., 100.]]), np.array([9], np.int64), np.array([0., 1.]),
                         np.zeros((2, 4)), 1e-6, d.core.hull.common.Vehicle(),
                         {'contact_lower_s': np.array([np.nan])})
            output = fn('synthetic', {'union_indices': [9]}, candidate)
        self.assertTrue(output['summary']['strict_prefix_gate_passed'])
        self.assertEqual(saved['arrays']['candidate_lower_s'].dtype, np.float64)
        self.assertTrue(np.isnan(saved['arrays']['candidate_lower_s'][0]))
        self.assertEqual(saved['arrays']['union_index'][0], 9)

    def test_execution_restores_v2_run_after_exception(self):
        with patch.object(d.previous, 'execution', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):
                d.execution()
        self.assertEqual(d.r.RUN, d.RUN)

    def test_no_old_used_entries_called_by_lossless_encoder(self):
        with patch.object(d.previous, 'run', side_effect=AssertionError('old run')), \
             patch.object(d.previous, 'close', side_effect=AssertionError('old close')):
            stub, packed = s.encode_record(self.raw)
            self.assertEqual(s.decode_record(stub, packed)[0], self.raw)


if __name__ == '__main__':
    unittest.main()
