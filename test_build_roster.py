import json, os, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_roster as br

SAMPLE = {
    'status': 'OK',
    'sessionpeople': {
        'session': {'session_id': 2100},
        'people': [
            {'people_id': 1, 'party': 'R', 'role': 'Sen', 'name': 'Stephen A. Huffman',
             'first_name': 'Stephen', 'middle_name': 'A.', 'last_name': 'Huffman',
             'suffix': '', 'nickname': '', 'district': 'SD-005'},
            {'people_id': 2, 'party': 'R', 'role': 'Rep', 'name': 'Matt Huffman',
             'first_name': 'Matthew', 'middle_name': '', 'last_name': 'Huffman',
             'suffix': '', 'nickname': 'Matt', 'district': 'HD-078'},
            {'people_id': 3, 'party': 'D', 'role': 'Sen', 'name': 'Willis Blackshear Jr.',
             'first_name': 'Willis', 'middle_name': '', 'last_name': 'Blackshear',
             'suffix': 'Jr.', 'nickname': '', 'district': 'SD-005'},
        ],
    },
}


class TestParsePeople(unittest.TestCase):
    def test_maps_role_to_chamber_and_parses_district(self):
        people = br.parse_people(SAMPLE)
        by_id = {p['people_id']: p for p in people}
        self.assertEqual(by_id[1]['chamber'], 'senate')
        self.assertEqual(by_id[2]['chamber'], 'house')
        self.assertEqual(by_id[1]['district'], 5)
        self.assertEqual(by_id[2]['district'], 78)
        self.assertEqual(by_id[2]['nickname'], 'Matt')
        self.assertEqual(by_id[3]['suffix'], 'Jr.')

    def test_empty_or_error_payload_yields_empty_list(self):
        self.assertEqual(br.parse_people(None), [])
        self.assertEqual(br.parse_people({'status': 'ERROR'}), [])

    def test_build_roster_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'roster.json')
            with mock.patch.object(br.fetcher, 'call_legiscan_api', return_value=SAMPLE):
                members = br.build_roster(2100, out_path=out)
            self.assertEqual(len(members), 3)
            self.assertEqual(json.load(open(out, encoding='utf-8'))[0]['last'], 'Huffman')


if __name__ == '__main__':
    unittest.main()
