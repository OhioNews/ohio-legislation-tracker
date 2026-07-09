import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roster_enrich as re_

ROSTER = [
    {'people_id': 1, 'name': 'Robert McColley', 'first': 'Robert', 'last': 'McColley',
     'middle': '', 'nickname': '', 'suffix': '', 'party': 'R', 'chamber': 'senate', 'district': 1},
    {'people_id': 2, 'name': 'Beth Liston', 'first': 'Beth', 'last': 'Liston',
     'middle': '', 'nickname': '', 'suffix': '', 'party': 'D', 'chamber': 'senate', 'district': 3},
    {'people_id': 3, 'name': 'Kristina Roegner', 'first': 'Kristina', 'last': 'Roegner',
     'middle': '', 'nickname': '', 'suffix': '', 'party': 'R', 'chamber': 'senate', 'district': 27},
]


def program(sections, captions, chamber='SENATE'):
    return {'program': {'id': 1, 'chamber': chamber}, 'captions': captions, 'sections': sections}


class TestScanIntroWindow(unittest.TestCase):
    def test_title_anchored_names_are_found(self):
        d = program(
            [{'start': 0, 'end': 300, 'type': 'Convene Session/Invocation',
              'bills': [], 'persons': []}],
            [[10.0, 'Senator McColley, you are recognized.'],
             [20.0, 'the gentlelady from the 27th, Ms. Roegner.']],
        )
        ids = {m['people_id'] for m in re_.scan_intro_window(d, ROSTER)}
        self.assertEqual(ids, {1, 3})

    def test_bare_mention_is_ignored(self):
        d = program(
            [{'start': 0, 'end': 300, 'type': 'Convene Session/Invocation',
              'bills': [], 'persons': []}],
            [[10.0, 'I want to thank Liston for the coffee.']],
        )
        self.assertEqual(re_.scan_intro_window(d, ROSTER), [])

    def test_scan_stops_after_intro_window(self):
        d = program(
            [{'start': 0, 'end': 100, 'type': 'Convene Session/Invocation',
              'bills': [], 'persons': []},
             {'start': 100, 'end': 900, 'type': 'Resolution', 'bills': [], 'persons': []}],
            [[500.0, 'Senator McColley moves adoption.']],  # outside intro window
        )
        self.assertEqual(re_.scan_intro_window(d, ROSTER), [])


class TestEnrichSpeakers(unittest.TestCase):
    def test_marker_name_enriched_with_party_district(self):
        d = program([{'start': 0, 'end': 300, 'type': 'Resolution',
                      'bills': [], 'persons': ['Robert McColley']}], [])
        out = re_.enrich_speakers(d, ROSTER)
        self.assertEqual(out, [{'name': 'Robert McColley', 'party': 'R', 'district': 1,
                                'chamber': 'senate', 'source': 'marker', 'matched': True}])

    def test_unmatched_marker_name_kept_without_authority(self):
        d = program([{'start': 0, 'end': 300, 'type': 'Convene Session/Invocation',
                      'bills': [], 'persons': ['Pastor Peter Marcis']}], [])
        out = re_.enrich_speakers(d, ROSTER)
        self.assertEqual(out[0], {'name': 'Pastor Peter Marcis', 'party': None,
                                  'district': None, 'chamber': None,
                                  'source': 'marker', 'matched': False})

    def test_intro_scan_adds_missed_member_and_both_source(self):
        d = program(
            [{'start': 0, 'end': 300, 'type': 'Convene Session/Invocation',
              'bills': [], 'persons': ['Robert McColley']}],
            [[10.0, 'Senator McColley and Senator Roegner, welcome.']],
        )
        out = {s['name']: s for s in re_.enrich_speakers(d, ROSTER)}
        self.assertEqual(out['Robert McColley']['source'], 'both')
        self.assertEqual(out['Kristina Roegner']['source'], 'intro-scan')
        self.assertTrue(out['Kristina Roegner']['matched'])

    def test_no_roster_all_unmatched(self):
        d = program([{'start': 0, 'end': 300, 'type': 'Resolution',
                      'bills': [], 'persons': ['Robert McColley']}], [])
        out = re_.enrich_speakers(d, [])
        self.assertEqual(out[0]['matched'], False)
        self.assertEqual(out[0]['name'], 'Robert McColley')


if __name__ == '__main__':
    unittest.main()
