"""Tests for transcript_relevance.py. Run: python -m unittest test_transcript_relevance -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transcript_relevance as rel


def distilled(lines):
    # lines: list of (start, text)
    return {'program': {}, 'captions': [[float(s), t] for s, t in lines], 'sections': []}


class WordBoundaryTests(unittest.TestCase):
    def test_whole_word_only_no_substring(self):
        pats = rel.compile_aliases(['rent', 'gun'])
        # "current", "parent", "begun" must NOT match
        self.assertEqual(rel.line_matches("the current parent has begun to worry", pats), 0)
        self.assertEqual(rel.line_matches("i cannot pay my rent and i own a gun", pats), 2)

    def test_case_insensitive(self):
        pats = rel.compile_aliases(['property tax'])
        self.assertEqual(rel.line_matches("The Property Tax debate continued", pats), 1)


class SubstanceTests(unittest.TestCase):
    # NB: alias 'data center' is singular; lines use singular "data center" so the
    # whole-word match fires (\bdata center\b does NOT match plural "data centers").
    def test_substantive_matches_skips_procedural(self):
        pats = rel.compile_aliases(['data center'])
        d = distilled([
            (0, "The proposed data center would pull enormous power from the regional grid."),  # match, non-proc
            (10, "Yes. No. Aye. Nay. Present. Absent."),  # roll-call -> skipped
            (20, "A single data center can use as much water as a small town each day."),  # match, non-proc
        ])
        self.assertEqual(rel.substantive_matches(d, pats), 2)

    def test_best_excerpt_prefers_substantive_and_appends_context(self):
        pats = rel.compile_aliases(['data center'])
        d = distilled([
            (0, "Data center."),  # trivial (<25 chars) -> procedural, skipped
            (10, "One data center can inflate load forecasts by about 40 percent, opponents argued."),
            (20, "That shifts the cost onto ordinary ratepayers."),
        ])
        ex = rel.best_excerpt(d, pats)
        self.assertIn("inflate load forecasts", ex)
        self.assertIn("shifts the cost", ex)  # next line appended for context

    def test_best_excerpt_escapes_html(self):
        pats = rel.compile_aliases(['data center'])
        d = distilled([(0, "This data center <script>alert(1)</script> would draw huge amounts of power.")])
        ex = rel.best_excerpt(d, pats)
        self.assertNotIn("<script>", ex)
        self.assertIn("&lt;script&gt;", ex)

    def test_best_excerpt_empty_when_no_match(self):
        pats = rel.compile_aliases(['marijuana'])
        d = distilled([(0, "This hearing is entirely about highway bridge repair funding levels.")])
        self.assertEqual(rel.best_excerpt(d, pats), '')


if __name__ == '__main__':
    unittest.main()
