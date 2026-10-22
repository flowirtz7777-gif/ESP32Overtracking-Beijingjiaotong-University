from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import sys
import unittest
from unittest.mock import patch

import resume_v3


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.original_deadline = resume_v3.runner.DEADLINE
        self.cp = {'source_signature': {'model.py': 'sha'}, 'completed': {'job': {}},
                   'stages': {'S0': {'done': True}}, 'status': 'deadline_saved'}

    def tearDown(self):
        resume_v3.runner.DEADLINE = self.original_deadline

    def test_check_only_starts_nothing(self):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['resume_v3.py', '--check-only']), \
             patch.object(resume_v3, 'inspect_checkpoint', return_value=self.cp), \
             patch.object(resume_v3.runner, 'main') as run, \
             patch.object(resume_v3, 'audit') as audit, \
             patch.object(resume_v3, 'write_json') as save, contextlib.redirect_stdout(out):
            resume_v3.main()
        run.assert_not_called()
        audit.assert_not_called()
        save.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['jobs_started_by_this_check'], 0)

    def test_explicit_deadline_recorded_without_changing_numeric_source(self):
        until = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0)
        saved = []
        with patch.object(sys, 'argv', ['resume_v3.py', '--until', until.isoformat(), '--workers', '4']), \
             patch.object(resume_v3, 'inspect_checkpoint', return_value=self.cp), \
             patch.object(resume_v3, 'audit') as audit, \
             patch.object(resume_v3, 'file_hash', return_value='sha'), \
             patch.object(resume_v3, 'write_json', side_effect=lambda path, obj: saved.append((path, dict(obj)))), \
             patch.object(resume_v3, 'read_json', return_value={'status': 'deadline_saved'}), \
             patch.object(resume_v3.runner, 'main') as run:
            resume_v3.main()
        audit.assert_called_once_with(resume_v3.runner.RUN)
        run.assert_called_once_with(4)
        self.assertEqual(resume_v3.runner.DEADLINE, until.timestamp())
        self.assertEqual(saved[-1][1]['deadline_utc'], until.isoformat())
        self.assertFalse(saved[-1][1]['numeric_source_changed'])
        self.assertEqual(saved[-1][1]['status'], 'deadline_saved')

    def test_deadline_and_worker_rejections_start_nothing(self):
        cases = [[], ['--until', '2020-01-01T00:00:00Z'],
                 ['--until', '2099-01-01T00:00:00'], ['--until', 'invalid'],
                 ['--check-only', '--workers', '9']]
        for arguments in cases:
            with self.subTest(arguments=arguments), \
                 patch.object(sys, 'argv', ['resume_v3.py', *arguments]), \
                 patch.object(resume_v3, 'inspect_checkpoint', return_value=self.cp), \
                 patch.object(resume_v3.runner, 'main') as run, \
                 patch.object(resume_v3, 'write_json') as save, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                resume_v3.main()
            run.assert_not_called()
            save.assert_not_called()

    def test_execution_failure_preserves_failed_session_record(self):
        until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        saved = []
        with patch.object(sys, 'argv', ['resume_v3.py', '--until', until]), \
             patch.object(resume_v3, 'inspect_checkpoint', return_value=self.cp), \
             patch.object(resume_v3, 'audit'), \
             patch.object(resume_v3, 'file_hash', return_value='sha'), \
             patch.object(resume_v3, 'write_json', side_effect=lambda path, obj: saved.append(dict(obj))), \
             patch.object(resume_v3.runner, 'main', side_effect=RuntimeError('locked')), \
             self.assertRaisesRegex(RuntimeError, 'locked'):
            resume_v3.main()
        self.assertEqual(saved[-1]['status'], 'failed')
        self.assertIn('ended_at_utc', saved[-1])

    def test_source_drift_rejected(self):
        with patch.object(resume_v3, 'read_json', return_value=self.cp), \
             patch.object(resume_v3.runner, 'signature', return_value={'model.py': 'changed'}), \
             self.assertRaisesRegex(RuntimeError, 'source changed'):
            resume_v3.inspect_checkpoint()

    def test_status_changes_do_not_hide_numeric_plan_changes(self):
        a = {'status': 'running', 'stages': [{'status': 'not_started', 'W': 2}]}
        b = {'status': 'checkpoint_saved', 'stages': [{'status': 'completed', 'W': 2}]}
        self.assertEqual(resume_v3.without_status(a), resume_v3.without_status(b))
        b['stages'][0]['W'] = 3
        self.assertNotEqual(resume_v3.without_status(a), resume_v3.without_status(b))


if __name__ == '__main__':
    unittest.main()
