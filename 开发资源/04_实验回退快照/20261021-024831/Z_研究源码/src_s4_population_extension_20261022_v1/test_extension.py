import copy
import datetime as dt
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import extension as x


def parent():
    completed = {}
    number = 0
    for k in range(23):
        ids = {}
        for _ in range(2 if k < 18 else 1):
            ids[str(number)] = {}
            number += 1
        completed[str(k)] = {'datasets': ids}
    return {'status': 'stopped_failure_or_deadline', 'failure': '24:00 new population group submission cutoff',
            'completed': completed, 'exact_reused_groups': list(range(12)), 'new_generated_groups': list(range(11))}


class ExtensionTests(unittest.TestCase):
    def test_deadline_literal_tomorrow_from_oct20(self):
        self.assertEqual(x.DEADLINE, dt.datetime(2026, 10, 21, 16, tzinfo=dt.timezone.utc))
        self.assertEqual(x.DEADLINE_LOCAL, '2026-10-22T00:00:00+08:00')

    def test_budget_and_reserve_and_scandir(self):
        x.configure()
        self.assertEqual(x.r.CAP, 32 * 1024**3)
        self.assertEqual(x.r.RESERVE, 3 * 1024**3)
        self.assertIs(x.r.tree_bytes, x.base.scan_size)

    def test_legacy_execution_temporarily_binds_old_auth(self):
        def evidence():
            self.assertEqual(x.r.AUTH, x.OLD_AUTH)
            return 'helper', {'idle': True}
        with patch.object(x.admin, 'stopped_evidence', side_effect=evidence):
            self.assertEqual(x.execution(), ('helper', {'idle': True}))
        self.assertEqual(x.r.AUTH, x.AUTH)
        self.assertEqual(x.r.DEADLINE, x.DEADLINE)

    def test_execution_exception_restores_new_budget_and_paths(self):
        with patch.object(x.admin, 'stopped_evidence', side_effect=RuntimeError('blocked')):
            with self.assertRaises(RuntimeError):
                x.execution()
        self.assertEqual(x.r.AUTH, x.AUTH)
        self.assertEqual(x.r.RUN, x.RUN)
        self.assertEqual(x.r.CAP, x.CAP)

    def test_parent_full_partial_accounting(self):
        with patch.object(Path, 'exists', return_value=False):
            x.check_parent(parent())

    def test_parent_non_deadline_failure_rejected(self):
        cp = parent()
        cp['failure'] = 'unknown numerical crash'
        with self.assertRaises(RuntimeError):
            x.check_parent(cp)

    def test_parent_running_rejected(self):
        cp = parent()
        cp['status'] = 'running'
        with self.assertRaises(RuntimeError):
            x.check_parent(cp)

    def test_missing_parent_group_rejected(self):
        cp = parent()
        cp['completed'].pop('0')
        with self.assertRaises(RuntimeError):
            x.check_parent(cp)

    def test_duplicate_parent_dataset_rejected(self):
        cp = parent()
        cp['completed']['22']['datasets'] = {'0': {}}
        with self.assertRaises(RuntimeError):
            x.check_parent(cp)

    def test_partial_parent_is_not_accepted(self):
        with patch.object(Path, 'exists', return_value=True):
            with self.assertRaises(RuntimeError):
                x.check_parent(parent())

    def test_partition_preserves_order_and_never_recalculates_parent(self):
        groups = {str(i): [] for i in range(39)}
        reused, missing = x.previous.partition(groups, parent()['completed'])
        self.assertEqual(reused, list(groups)[:23])
        self.assertEqual(missing, list(groups)[23:])

    def test_kernel_code_and_original_namespace_preserved(self):
        prior_run = x.base.RUN
        kernel = x.previous.bound_group_kernel(destination=x.RUN)
        self.assertIs(kernel.__code__, x.base.process_group.__code__)
        self.assertEqual(kernel.__globals__['RUN'], x.RUN)
        self.assertEqual(x.base.RUN, prior_run)

    def test_current_and_parent_paths_disjoint(self):
        self.assertNotEqual(x.RUN, x.PARENT)
        self.assertNotEqual(x.AUTH, x.previous.AUTH)
        self.assertFalse(x.RUN.is_relative_to(x.PARENT))

    def test_lossless_administrative_payload(self):
        self.assertEqual(x.gzip.decompress(x.packed({'values': [1, 2, 3]})), x.r.encoded({'values': [1, 2, 3]}))

    def test_projections_include_every_dataset(self):
        with self.assertRaises(RuntimeError):
            x.validate_asset('g', {'datasets': {}}, {}, {'g': ['a']}, Path('synthetic'))

    def check_synthetic_asset(self, index=None, stored=None, bits=None, offset=False):
        xy = np.array([[0., 0.], [1., 1.]])
        target = {'xy': xy[::-1].copy()}
        status = np.array([0, 1], dtype=np.uint8)
        combined = {'contact_status': status}
        arrays = {'xy': xy + (1 if offset else 0), 'oldpath__contact_status': status,
                  'independent__contact_status': status, 'combined__contact_status': status}
        index = np.array([1, 0], dtype=np.int32) if index is None else index
        projected = status[::-1].copy() if stored is None else stored
        mask = np.array([True, False])
        out = {'union_index': index, 'combined__contact_status': projected,
               'changed__packbits': np.packbits(mask, bitorder='little') if bits is None else bits}
        entry = {'group': {'result_sha256': 'sha'}, 'datasets': {'a': {'result_sha256': 'sha'}}}
        with patch.object(x.base, 'read_arrays', side_effect=[(arrays, {}), (out, {'summary': {'changed': 1}})]), \
             patch.object(x.r, 'file_hash', return_value='sha'), \
             patch.object(x.base, 'combine', return_value=combined), \
             patch.object(x.base, 'old_discrepancies', return_value={'changed': mask}):
            return x.validate_asset('g', entry, {'a': {'target': target}}, {'g': ['a']}, Path('synthetic'))

    def test_full_array_exact_reuse_passes(self):
        self.check_synthetic_asset()

    def test_changed_coordinate_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_synthetic_asset(offset=True)

    def test_out_of_range_projection_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_synthetic_asset(index=np.array([1, 2], dtype=np.int32))

    def test_wrong_projection_order_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_synthetic_asset(index=np.array([0, 1], dtype=np.int32))

    def test_changed_related_quantity_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_synthetic_asset(stored=np.array([0, 1], dtype=np.uint8))

    def test_packbits_padding_and_indices_checked(self):
        with self.assertRaises(RuntimeError):
            self.check_synthetic_asset(bits=np.array([129], dtype=np.uint8))


if __name__ == '__main__':
    unittest.main()
