"""Tests for build_transcript_derived.py. Run: python -m unittest test_build_transcript_derived -v"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_transcript_derived as bd
import transcript_distill as dm


def make_distilled(tmp, pid, date, text_lines, bills=None, series_id=26):
    d = {'program': {'id': pid, 'name': f'P{pid}', 'release_date': date, 'duration': 3600,
                     'series_id': series_id, 'series_name': 'House', 'chamber': 'HOUSE'},
         'captions': [[float(i * 10), t] for i, t in enumerate(text_lines)],
         'sections': [{'start': 0, 'end': 3600, 'type': '', 'label': 'Full session',
                       'bills': bills or [], 'persons': ['Angela King'] if series_id in (25, 26) else []}]}
    dm.save_distilled(d, tmp)
    return d


class DerivedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_index_includes_captionless_greyed(self):
        make_distilled(self.tmp, 1, '2026-06-10', ['hello'])
        state = {'1': {'status': 'archived'},
                 '2': {'status': 'awaiting_captions', 'name': 'P2', 'release_date': '2026-06-11'}}
        idx, _ = bd.build_index_and_topics(self.tmp, state, [], now='2026-07-06')
        self.assertEqual(len(idx), 2)
        self.assertEqual(idx[0]['id'], 2)          # newest first
        self.assertFalse(idx[0]['captions'])
        self.assertTrue(idx[1]['captions'])
        self.assertEqual(idx[1]['speakers'], ['Angela King'])

    def test_topic_counts_and_bill_attribution(self):
        make_distilled(self.tmp, 1, '2026-06-10', ['the property tax levy would shift'], bills=['HB 335'])
        make_distilled(self.tmp, 2, '2026-01-01', ['property taxes again'])      # outside 90d
        make_distilled(self.tmp, 3, '2026-06-11', ['nothing relevant here'])
        curated = [{'slug': 'property-taxes', 'name': 'Property taxes',
                    'aliases': ['property tax', 'property taxes']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        t = topics['property-taxes']
        self.assertEqual(t['meeting_count_90d'], 1)
        self.assertEqual(sorted(t['program_ids']), [1, 2])
        self.assertEqual(t['bills'], ['HB 335'])

    def test_alias_match_is_case_insensitive(self):
        make_distilled(self.tmp, 1, '2026-06-10', ['The Property Tax debate'])
        curated = [{'slug': 'pt', 'name': 'PT', 'aliases': ['property tax']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        self.assertEqual(topics['pt']['program_ids'], [1])


if __name__ == '__main__':
    unittest.main()
