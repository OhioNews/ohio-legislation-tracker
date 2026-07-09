import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roster_match as rm

ROSTER = [
    {'people_id': 1, 'name': 'Stephen A. Huffman', 'first': 'Stephen', 'last': 'Huffman',
     'middle': 'A.', 'nickname': '', 'suffix': '', 'party': 'R', 'chamber': 'senate', 'district': 5},
    {'people_id': 2, 'name': 'Matt Huffman', 'first': 'Matthew', 'last': 'Huffman',
     'middle': '', 'nickname': 'Matt', 'suffix': '', 'party': 'R', 'chamber': 'house', 'district': 78},
    {'people_id': 3, 'name': 'Steve Wilson', 'first': 'Stephen', 'last': 'Wilson',
     'middle': 'A.', 'nickname': 'Steve', 'suffix': '', 'party': 'R', 'chamber': 'senate', 'district': 7},
    {'people_id': 4, 'name': 'Willis Blackshear Jr.', 'first': 'Willis', 'last': 'Blackshear',
     'middle': '', 'nickname': '', 'suffix': 'Jr.', 'party': 'D', 'chamber': 'house', 'district': 39},
]


class TestMatchName(unittest.TestCase):
    def test_full_name_with_middle_initial(self):
        self.assertEqual(rm.match_name('Stephen A. Huffman', 'senate', ROSTER)['people_id'], 1)

    def test_full_name_wins_over_chamber_constraint(self):
        # Senate program recognizes House member by full name -> resolves to House member
        self.assertEqual(rm.match_name('Matt Huffman', 'senate', ROSTER)['people_id'], 2)

    def test_nickname_matches(self):
        self.assertEqual(rm.match_name('Steve Wilson', 'senate', ROSTER)['people_id'], 3)

    def test_suffix_stripped(self):
        self.assertEqual(rm.match_name('Willis Blackshear Jr.', 'house', ROSTER)['people_id'], 4)

    def test_bare_last_name_disambiguated_by_chamber(self):
        self.assertEqual(rm.match_name('Huffman', 'senate', ROSTER)['people_id'], 1)
        self.assertEqual(rm.match_name('Huffman', 'house', ROSTER)['people_id'], 2)

    def test_bare_last_name_ambiguous_without_chamber_returns_none(self):
        self.assertIsNone(rm.match_name('Huffman', None, ROSTER))

    def test_unknown_name_returns_none(self):
        self.assertIsNone(rm.match_name('Pastor Peter Marcis', 'senate', ROSTER))

    def test_empty_roster_returns_none(self):
        self.assertIsNone(rm.match_name('Matt Huffman', 'house', []))


if __name__ == '__main__':
    unittest.main()
