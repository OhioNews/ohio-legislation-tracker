"""Tests for build_transcript_derived.py. Run: python -m unittest test_build_transcript_derived -v"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_transcript_derived as bd
import transcript_distill as dm


def make_distilled(tmp, pid, date, lines, bills=None, series_id=1002063):
    # lines: list of caption text strings, spaced 10s apart
    d = {'program': {'id': pid, 'name': 'P%d' % pid, 'release_date': date, 'duration': 3600,
                     'series_id': series_id, 'series_name': 'Committee', 'chamber': 'HOUSE'},
         'captions': [[float(i * 10), t] for i, t in enumerate(lines)],
         'sections': [{'start': 0, 'end': 3600, 'type': '', 'label': 'Full session',
                       'bills': bills or [], 'persons': []}]}
    dm.save_distilled(d, tmp)
    return d


def rich_lines(term, n):
    # n non-procedural lines that each match `term` (each > 25 chars)
    return ["The committee heard extended testimony about %s and its effects today." % term
            for _ in range(n)]


class DerivedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_topic_included_only_above_threshold(self):
        make_distilled(self.tmp, 1, '2026-06-10', rich_lines('data centers', 10))  # >=8 -> in
        make_distilled(self.tmp, 2, '2026-06-11', rich_lines('data centers', 3))   # <8 -> out
        curated = [{'slug': 'data-centers', 'name': 'Data centers', 'brief': 'B',
                    'aliases': ['data centers']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        t = topics['data-centers']
        self.assertEqual(t['total'], 1)
        self.assertEqual([m['id'] for m in t['meetings']], [1])
        self.assertEqual(t['brief'], 'B')

    def test_meetings_ranked_by_matches_desc(self):
        make_distilled(self.tmp, 1, '2026-06-01', rich_lines('housing', 9))
        make_distilled(self.tmp, 2, '2026-06-02', rich_lines('housing', 20))
        curated = [{'slug': 'housing', 'name': 'Housing', 'brief': '', 'aliases': ['housing']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        ids = [m['id'] for m in topics['housing']['meetings']]
        self.assertEqual(ids, [2, 1])  # 20 matches before 9

    def test_recent_window(self):
        make_distilled(self.tmp, 1, '2026-06-10', rich_lines('marijuana', 10))  # within 90d of 2026-07-06
        make_distilled(self.tmp, 2, '2026-01-01', rich_lines('marijuana', 10))  # outside
        curated = [{'slug': 'marijuana', 'name': 'M', 'brief': '', 'aliases': ['marijuana']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        self.assertEqual(topics['marijuana']['total'], 2)
        self.assertEqual(topics['marijuana']['recent'], 1)

    def test_meeting_has_excerpt_and_bill(self):
        make_distilled(self.tmp, 1, '2026-06-10',
                       rich_lines('data centers', 10), bills=['HB 15'])
        curated = [{'slug': 'data-centers', 'name': 'D', 'brief': '', 'aliases': ['data centers']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        m = topics['data-centers']['meetings'][0]
        self.assertTrue(m['excerpt'])
        self.assertIn('HB 15', m['bills'])
        self.assertIn('HB 15', topics['data-centers']['bills'])

    def test_word_boundary_no_substring_inflation(self):
        # "rent" must NOT match "current/parent/different"
        make_distilled(self.tmp, 1, '2026-06-10',
                       ["The current parent had a different apparent arrangement entirely here."] * 10)
        curated = [{'slug': 'housing', 'name': 'H', 'brief': '', 'aliases': ['rent']}]
        _, topics = bd.build_index_and_topics(self.tmp, {}, curated, now='2026-07-06')
        self.assertEqual(topics['housing']['total'], 0)


if __name__ == '__main__':
    unittest.main()
