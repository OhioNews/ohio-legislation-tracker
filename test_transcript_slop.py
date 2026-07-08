"""Tests for transcript_slop.py. Run: python -m unittest test_transcript_slop -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transcript_slop as slop


class SlopTests(unittest.TestCase):
    def test_roll_call_vote_tokens_flagged(self):
        self.assertTrue(slop.is_procedural(
            "Johnson. Yes. Kaler. No. Landis. Yes. Manning. No. Peyton. Yes."))

    def test_name_list_flagged(self):
        self.assertTrue(slop.is_procedural(
            "Gavron. Hoffman. Ingram. Johnson. Kaler. Landis. Manchester."))

    def test_gavel_phrase_only_flagged(self):
        self.assertTrue(slop.is_procedural("Without objection, so ordered."))
        self.assertTrue(slop.is_procedural("The clerk will call the roll."))
        self.assertTrue(slop.is_procedural("Seeing none, hearing none."))

    def test_trivial_short_line_flagged(self):
        self.assertTrue(slop.is_procedural("Thank you."))
        self.assertTrue(slop.is_procedural("Yes."))

    def test_substantive_testimony_not_flagged(self):
        self.assertFalse(slop.is_procedural(
            "Utilities inflate their load forecasts by about 40% per data center, "
            "which shifts costs onto ordinary ratepayers."))

    def test_gavel_phrase_plus_substance_not_flagged(self):
        # blocklist phrase present, but real content beyond it -> keep
        self.assertFalse(slop.is_procedural(
            "Thank you for the opportunity to explain how property taxes hurt seniors "
            "on fixed incomes across rural counties."))

    def test_empty_and_none(self):
        self.assertTrue(slop.is_procedural(""))
        self.assertTrue(slop.is_procedural(None))


if __name__ == '__main__':
    unittest.main()
