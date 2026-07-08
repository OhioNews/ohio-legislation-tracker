"""Tests for the curated topic slate. Run: python -m unittest test_topics_curated -v"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'ohio_transcript_data', 'topics_curated.json')


class CuratedTests(unittest.TestCase):
    def setUp(self):
        with open(PATH, encoding='utf-8') as f:
            self.topics = json.load(f)

    def test_twelve_topics(self):
        self.assertEqual(len(self.topics), 12)

    def test_required_keys_and_types(self):
        slugs = set()
        for t in self.topics:
            self.assertIn('slug', t); self.assertIn('name', t)
            self.assertIn('aliases', t); self.assertIn('brief', t)
            self.assertIsInstance(t['aliases'], list)
            self.assertTrue(t['aliases'])
            self.assertIsInstance(t['brief'], str)  # may be empty until Scott writes it
            slugs.add(t['slug'])
        self.assertEqual(len(slugs), 12)  # unique slugs

    def test_expected_slugs_present(self):
        slugs = {t['slug'] for t in self.topics}
        self.assertEqual(slugs, {
            'health-care', 'public-safety', 'education', 'jobs-economy',
            'elections', 'energy', 'property-taxes', 'child-care',
            'data-centers', 'housing', 'abortion', 'lgbtq'})

    def test_public_safety_includes_guns(self):
        ps = next(t for t in self.topics if t['slug'] == 'public-safety')
        self.assertIn('concealed carry', ps['aliases'])


if __name__ == '__main__':
    unittest.main()
