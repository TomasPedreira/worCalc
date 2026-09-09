import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worcalc.diagnostics import read_observed_impacts, record_calculation, _loggers


class DiagnosticTests(unittest.TestCase):
    def test_writes_timestamped_json_and_rotates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shots.jsonl'
            try:
                record_calculation({'reason': 'terrain_obstruction', 'range_yards': 407}, path)
                row = json.loads(path.read_text())
                self.assertIn('timestamp_utc', row)
                self.assertEqual(row['range_yards'], 407)
                handler = _loggers[path].handlers[0]
                handler.maxBytes = 200
                for index in range(10):
                    record_calculation({'reason': 'clear', 'index': index}, path)
                self.assertLessEqual(len(list(Path(directory).glob('shots.jsonl*'))), 3)
                self.assertEqual(json.loads(path.read_text().splitlines()[-1])['index'], 9)
            finally:
                logger = _loggers.pop(path, None)
                if logger:
                    for handler in logger.handlers:
                        handler.close()

    def test_unwritable_log_does_not_break_calculation(self):
        with patch('worcalc.diagnostics.RotatingFileHandler', side_effect=OSError('read only')):
            with self.assertLogs('worcalc.diagnostics', level='WARNING'):
                record_calculation({'reason': 'clear'}, Path('unwritable-test.jsonl'))

    def test_reads_observations_across_rotated_files_and_skips_bad_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shots.jsonl'
            path.with_name('shots.jsonl.1').write_text(
                '{bad json}\n' + json.dumps({'event': 'observed_impact', 'impact_id': 'old'}),
                encoding='utf-8',
            )
            path.write_text(
                json.dumps({'event': 'observed_impact', 'impact_id': 'new'}),
                encoding='utf-8',
            )

            self.assertEqual(
                [event['impact_id'] for event in read_observed_impacts(path)],
                ['old', 'new'],
            )
