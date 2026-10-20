import unittest
from pathlib import Path
from recovery import bound_group_kernel, partition, check_gate, base


class RecoveryTests(unittest.TestCase):
    def test_exact_kernel_code_not_reimplemented(self):
        self.assertIs(bound_group_kernel().__code__, base.process_group.__code__)

    def test_output_directory_isolated_without_changing_frozen_module(self):
        previous = base.RUN
        bound = bound_group_kernel(destination=Path('new-output'))
        self.assertEqual(bound.__globals__['RUN'], Path('new-output'))
        self.assertEqual(base.RUN, previous)

    def test_partition_preserves_original_order_and_no_rerun(self):
        self.assertEqual(partition({'a': [], 'b': [], 'c': []}, {'b': {}}), (['b'], ['a', 'c']))

    def test_unknown_reused_group_rejected(self):
        with self.assertRaises(RuntimeError):
            partition({'a': []}, {'b': {}})

    def test_failed_prefix_gate_cannot_propagate(self):
        with self.assertRaises(RuntimeError):
            check_gate({'strict_all_point_prefix_gate_passed': False, 'generated_groups_audited': 12,
                        'generated_dataset_files': 30})

    def test_incomplete_gate_cannot_propagate(self):
        with self.assertRaises(RuntimeError):
            check_gate({'strict_all_point_prefix_gate_passed': True, 'generated_groups_audited': 11,
                        'generated_dataset_files': 30})

    def test_true_full_gate_admitted(self):
        check_gate({'strict_all_point_prefix_gate_passed': True, 'generated_groups_audited': 12,
                    'generated_dataset_files': 30})


if __name__ == '__main__':
    unittest.main()
