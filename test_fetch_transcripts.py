"""Tests for fetch_transcripts.py. Run: python -m unittest test_fetch_transcripts -v
Mocks the ohiochannel_api boundary; offline."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_transcripts as ft


def prog(pid, date, series_id=26, name=None):
    return {'id': pid, 'fullName': name or f'Program {pid}',
            'releaseDate': f'{date} 00:00:00', 'duration': 3600,
            'series': {'id': series_id, 'name': 'Series', 'chamber': 'HOUSE'}}


CAPTIONS = [{'startTime': 1.0, 'duration': 2.0, 'text': 'hello world'}]


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [
            mock.patch.object(ft, 'DATA_DIR', self.tmp),
            mock.patch.object(ft, 'PROGRAMS_DIR', os.path.join(self.tmp, 'programs')),
            mock.patch.object(ft, 'STATE_FILE', os.path.join(self.tmp, 'state.json')),
            mock.patch.object(ft, 'META_FILE', os.path.join(self.tmp, 'meta.json')),
            mock.patch.object(ft, 'SERIES_CONFIG', os.path.join(self.tmp, 'series.json')),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)


class DiscoverTests(TempDirCase):
    def test_stops_at_ga_start(self):
        pages = {'records': [prog(3, '2026-06-10'), prog(2, '2025-02-01'), prog(1, '2024-12-01')]}
        with mock.patch('fetch_transcripts.api.list_programs', return_value=pages):
            found = ft.discover_programs({'id': 26}, '2025-01-01', {}, backfill=False)
        self.assertEqual([p['id'] for p in found], [3, 2])

    def test_stops_at_archived_watermark_when_not_backfill(self):
        pages = {'records': [prog(3, '2026-06-10'), prog(2, '2026-06-09'), prog(1, '2026-06-03')]}
        state = {'2': {'status': 'archived'}}
        with mock.patch('fetch_transcripts.api.list_programs', return_value=pages):
            found = ft.discover_programs({'id': 26}, '2025-01-01', state, backfill=False)
        self.assertEqual([p['id'] for p in found], [3])

    def test_backfill_skips_known_but_continues(self):
        page1 = {'records': [prog(3, '2026-06-10'), prog(2, '2026-06-09')]}
        page2 = {'records': [prog(1, '2026-06-03')]}
        page3 = {'records': []}
        state = {'2': {'status': 'archived'}}
        with mock.patch('fetch_transcripts.api.list_programs', side_effect=[page1, page2, page3]):
            found = ft.discover_programs({'id': 26}, '2025-01-01', state, backfill=True)
        self.assertEqual([p['id'] for p in found], [3, 1])


class ProcessTests(TempDirCase):
    def test_archives_program_with_captions(self):
        state = {}
        with mock.patch('fetch_transcripts.api.get_captions', return_value=CAPTIONS), \
             mock.patch('fetch_transcripts.api.get_markers', return_value=[]):
            status = ft.process_program(prog(42, '2026-06-10'), state)
        self.assertEqual(status, 'archived')
        self.assertTrue(os.path.exists(os.path.join(ft.PROGRAMS_DIR, '42.json.gz')))
        self.assertEqual(state['42']['status'], 'archived')

    def test_captionless_waits_then_gives_up_after_14_days(self):
        state = {}
        with mock.patch('fetch_transcripts.api.get_captions', return_value=[]):
            s1 = ft.process_program(prog(43, '2026-06-10'), state, today='2026-06-11')
            self.assertEqual(s1, 'awaiting_captions')
            self.assertIn('program', state['43'])  # kept for recheck
            s2 = ft.process_program(state['43']['program'], state, today='2026-06-20')
            self.assertEqual(s2, 'awaiting_captions')
            s3 = ft.process_program(state['43']['program'], state, today='2026-06-27')
            self.assertEqual(s3, 'captions_unavailable')

    def test_late_captions_get_archived_on_recheck(self):
        state = {}
        with mock.patch('fetch_transcripts.api.get_captions', return_value=[]):
            ft.process_program(prog(44, '2026-06-10'), state, today='2026-06-11')
        with mock.patch('fetch_transcripts.api.get_captions', return_value=CAPTIONS), \
             mock.patch('fetch_transcripts.api.get_markers', return_value=[]):
            status = ft.process_program(state['44']['program'], state, today='2026-06-13')
        self.assertEqual(status, 'archived')


class MainTests(TempDirCase):
    def test_main_rechecks_awaiting_and_writes_meta(self):
        os.makedirs(self.tmp, exist_ok=True)
        with open(ft.SERIES_CONFIG, 'w') as f:
            json.dump({'ga_start_date': '2025-01-01',
                       'series': [{'id': 26, 'name': 'House', 'chamber': 'HOUSE', 'is_floor': True}]}, f)
        with open(ft.STATE_FILE, 'w') as f:
            json.dump({'44': {'status': 'awaiting_captions', 'first_seen': '2026-06-11',
                              'release_date': '2026-06-10', 'name': 'P44',
                              'program': prog(44, '2026-06-10')}}, f)
        with mock.patch('fetch_transcripts.api.list_programs', return_value={'records': []}), \
             mock.patch('fetch_transcripts.api.get_captions', return_value=CAPTIONS), \
             mock.patch('fetch_transcripts.api.get_markers', return_value=[]):
            rc = ft.main([])
        self.assertEqual(rc, 0)
        meta = json.load(open(ft.META_FILE))
        self.assertEqual(meta['archived_total'], 1)
        state = json.load(open(ft.STATE_FILE))
        self.assertEqual(state['44']['status'], 'archived')


if __name__ == '__main__':
    unittest.main()
