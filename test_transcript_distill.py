"""Tests for transcript_distill.py. Run: python -m unittest test_transcript_distill -v"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transcript_distill as dm


def program_fixture():
    return {'id': 208562, 'fullName': 'Ohio House of Representatives - 6-10-2026',
            'releaseDate': '2026-06-10 00:00:00', 'duration': 9614,
            'series': {'id': 26, 'name': 'Ohio House of Representatives', 'chamber': 'HOUSE'}}


def captions_fixture():
    return [{'startTime': 219.5, 'duration': 2.0, 'text': 'a resolution honoring'},
            {'startTime': 0.633, 'duration': 2.5, 'text': 'Prayer text'},
            {'startTime': 1840.0, 'duration': 2.0, 'text': 'third consideration of senate bill'}]


def markers_fixture():
    return [
        {'time': 0, 'description': 'Prayer by Pastor Zach',
         'markerType': {'name': 'Convene Session/Invocation'}, 'person': None,
         'legislationType': None, 'legislationNumber': None, 'children': []},
        {'time': 219, 'description': None, 'markerType': {'name': 'Resolution'},
         'person': None, 'legislationType': None, 'legislationNumber': None,
         'children': [{'time': 220, 'person': {'displayName': 'Angela King'},
                       'markerType': None, 'legislationType': None,
                       'legislationNumber': None, 'children': [], 'description': None}]},
        {'time': 1840, 'description': None, 'markerType': {'name': 'Third Consideration'},
         'person': None, 'legislationType': 'SENATE_BILL', 'legislationNumber': 162,
         'children': []},
    ]


class BillLabelTests(unittest.TestCase):
    def test_maps_types(self):
        self.assertEqual(dm.bill_label({'legislationType': 'SENATE_BILL', 'legislationNumber': 162}), 'SB 162')
        self.assertEqual(dm.bill_label({'legislationType': 'HOUSE_JOINT_RESOLUTION', 'legislationNumber': 10}), 'HJR 10')
        self.assertIsNone(dm.bill_label({'legislationType': None, 'legislationNumber': None}))


class SectionTests(unittest.TestCase):
    def test_sections_span_to_next_marker(self):
        secs = dm.build_sections(markers_fixture(), 9614)
        self.assertEqual([s['start'] for s in secs], [0, 219, 1840])
        self.assertEqual(secs[0]['end'], 219)
        self.assertEqual(secs[1]['end'], 1840)
        self.assertEqual(secs[2]['end'], 9614)

    def test_descendant_persons_and_bills_bubble_up(self):
        secs = dm.build_sections(markers_fixture(), 9614)
        self.assertEqual(secs[1]['persons'], ['Angela King'])
        self.assertEqual(secs[2]['bills'], ['SB 162'])
        self.assertIn('SB 162', secs[2]['label'])

    def test_markerless_yields_full_session(self):
        secs = dm.build_sections([], 15358)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]['label'], 'Full session')
        self.assertEqual((secs[0]['start'], secs[0]['end']), (0, 15358))

    def test_section_for_boundary_is_start_inclusive(self):
        secs = dm.build_sections(markers_fixture(), 9614)
        self.assertEqual(dm.section_for(secs, 219)['start'], 219)   # exactly at boundary -> later section
        self.assertEqual(dm.section_for(secs, 218.9)['start'], 0)
        self.assertEqual(dm.section_for(secs, 9000)['start'], 1840)


class DistillTests(unittest.TestCase):
    def test_distill_shape_and_sorting(self):
        d = dm.distill(program_fixture(), captions_fixture(), markers_fixture())
        self.assertEqual(d['program']['release_date'], '2026-06-10')
        self.assertEqual(d['program']['chamber'], 'HOUSE')
        starts = [c[0] for c in d['captions']]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(len(d['sections']), 3)

    def test_roundtrip_gzip(self):
        tmp = tempfile.mkdtemp()
        try:
            d = dm.distill(program_fixture(), captions_fixture(), markers_fixture())
            path = dm.save_distilled(d, tmp)
            self.assertTrue(path.endswith('208562.json.gz'))
            self.assertEqual(dm.load_distilled(path), d)
        finally:
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
