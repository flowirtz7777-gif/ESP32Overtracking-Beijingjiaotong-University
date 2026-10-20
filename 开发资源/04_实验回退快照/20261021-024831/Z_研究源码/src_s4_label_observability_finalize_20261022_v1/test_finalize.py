"""Pure synthetic JSON/text fixtures, no scientific data or computation."""
import copy
import json
import unittest
from pathlib import Path
import finalize as f


class FinalizeTests(unittest.TestCase):
    def fixture(self):
        counts = {'geometry_groups': 39, 'dataset_files': 57, 'group_unique_scope_points': 43670,
                  'selected_point_file_records': 51606, 'group_point_path_records_not_independent_samples': 87340}
        cp = {'status': 'complete_pending_independent_observability_close',
              'completed': {str(i): {'group': {'summary': {'points': 1000 if i < 38 else 5670}}} for i in range(39)},
              'accounting': counts}
        accepted = {'status': 'all_remaining_label_post_prefix_diagnostics_independently_checked_no_relabeling',
            'labels_and_prefix_proofs_unchanged': True, 'truth_asset_promotion_allowed': False,
            'accounting': counts, 'checks': {k: {tag: {'all_records': v['group']['summary']['points']}
                for tag in ('oldpath', 'independent')} for k, v in cp['completed'].items()}}
        stdout = '\n'.join('CLOSE CHECKED ALL UNKNOWN DIAGNOSTIC ROWS GROUP ' + str(i) for i in range(39))
        return cp, accepted, {'actual_wait_exit_code': 1}, stdout

    def test_existing_full_acceptance_only(self):
        self.assertEqual(f.eligible(*self.fixture())['selected_point_file_records'], 51606)

    def test_incomplete_scientific_checks_rejected(self):
        cp, a, exit_record, out = self.fixture(); a['checks'].pop('38')
        with self.assertRaises(ValueError):
            f.eligible(cp, a, exit_record, out)

    def test_duplicate_or_missing_group_log_rejected(self):
        cp, a, exit_record, out = self.fixture()
        with self.assertRaises(ValueError):
            f.eligible(cp, a, exit_record, out + '\nCLOSE CHECKED ALL UNKNOWN DIAGNOSTIC ROWS GROUP 1')

    def test_changed_scope_rejected(self):
        cp, a, exit_record, out = copy.deepcopy(self.fixture()); a['accounting']['selected_point_file_records'] = 1
        with self.assertRaises(ValueError):
            f.eligible(cp, a, exit_record, out)

    def test_wrong_exit_or_promoted_truth_rejected(self):
        cp, a, exit_record, out = self.fixture(); a['truth_asset_promotion_allowed'] = True
        with self.assertRaises(ValueError):
            f.eligible(cp, a, exit_record, out)

    def monitor(self):
        session = Path(r'Z:\synthetic\session')
        tail = ("Get-Content -LiteralPath '" + str(session / 'stdout.log') + "' -Tail 3\n"
            + "Get-Content -LiteralPath '" + str(session / 'stderr.log') + "' -Tail 12\n"
            + "Get-CimInstance Win32_Process -Filter 'ProcessId=37204' | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine | ConvertTo-Json\"")
        p = {'Name': 'pwsh.exe', 'ExecutablePath': r'C:\runtime\powershell\pwsh.exe',
             'CommandLine': 'pwsh -Command "' + tail}
        return session, p

    def test_exact_readonly_monitor_record(self):
        session, p = self.monitor()
        text = '_, after = execution()\nRuntimeError: Research processes remain: ' + json.dumps([p])
        self.assertEqual(f.monitor_failure(text, session), p)

    def test_any_additional_process_rejected(self):
        session, p = self.monitor()
        text = '_, after = execution()\nRuntimeError: Research processes remain: ' + json.dumps([p, p])
        with self.assertRaises(ValueError):
            f.monitor_failure(text, session)

    def test_unrecognized_command_or_scientific_process_rejected(self):
        session, p = self.monitor(); p['CommandLine'] += '; python science.py run'
        text = '_, after = execution()\nRuntimeError: Research processes remain: ' + json.dumps([p])
        with self.assertRaises(ValueError):
            f.monitor_failure(text, session)

    def test_earlier_scientific_failure_not_reinterpreted(self):
        with self.assertRaises(ValueError):
            f.monitor_failure('RuntimeError: geometry mismatch', Path('synthetic'))


if __name__ == '__main__':
    unittest.main()
