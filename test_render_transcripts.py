"""Tests for render_transcripts.py. Run: python -m unittest test_render_transcripts -v"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_transcripts as rt
import transcript_distill as dm


def distilled_fixture():
    return {'program': {'id': 208562, 'name': 'Ohio House <of> Representatives - 6-10-2026',
                        'release_date': '2026-06-10', 'duration': 200,
                        'series_id': 26, 'series_name': 'Ohio House of Representatives',
                        'chamber': 'HOUSE'},
            'captions': [[1.0, 'Prayer <script>alert(1)</script> text'],
                         [65.0, 'second chunk line'],
                         [130.0, 'inside the bill section']],
            'sections': [{'start': 0, 'end': 120, 'type': 'Convene Session/Invocation',
                          'label': 'Convene Session/Invocation', 'bills': [], 'persons': []},
                         {'start': 120, 'end': 200, 'type': 'Third Consideration',
                          'label': 'Third Consideration · SB 162', 'bills': ['SB 162'],
                          'persons': ['Angela King']}]}


class RenderProgramTests(unittest.TestCase):
    def setUp(self):
        self.html = rt.render_program(distilled_fixture())

    def test_escapes_api_strings(self):
        self.assertNotIn('<script>alert(1)</script>', self.html)
        self.assertIn('&lt;script&gt;', self.html)
        self.assertIn('Ohio House &lt;of&gt; Representatives', self.html)

    def test_chunk_anchors_every_60_seconds(self):
        self.assertIn('id="t1"', self.html)     # chunk starting at first caption (1s)
        self.assertIn('id="t65"', self.html)    # next 60s chunk
        self.assertIn('id="t130"', self.html)   # chunk inside second section

    def test_honesty_footer_verbatim(self):
        self.assertIn('Transcripts from Ohio Channel closed captions; '
                      'not an official record. Verify against video before quoting.', self.html)

    def test_pagefind_filters_and_meta(self):
        self.assertIn('data-pagefind-filter="chamber"', self.html)
        self.assertIn('data-pagefind-filter="speaker"', self.html)
        self.assertIn('Floor session', self.html)
        self.assertIn('data-pagefind-meta="bill_segments[data-json]"', self.html)
        self.assertIn('&quot;SB 162&quot;', self.html)  # bill segments JSON is escaped into attribute

    def test_bills_panel_has_jump_and_tracker_links(self):
        html_out = rt.render_program(distilled_fixture())
        # jump-to-moment anchor into this same transcript (SB 162 section starts at 120)
        self.assertIn('href="#t120"', html_out)
        # tracker link opens in a new tab with spaces stripped
        self.assertIn('ohio-legislation-tracker-LIVE.html?bill=SB162&ga=136', html_out)
        self.assertIn('target="_blank"', html_out)

    def test_bills_in_context_dedup_and_known_filter(self):
        d = {'program': {'id': 1, 'chamber': 'HOUSE'},
             'sections': [{'start': 0, 'end': 200, 'type': '', 'label': 'x',
                           'bills': ['HB 15'], 'persons': []}],
             'captions': [[50.0, 'We also discuss House Bill 9999 briefly.']]}
        # marker bill kept; scanned unknown bill dropped when known set provided
        out = rt.bills_in_context(d, known_bills={'HB 15'})
        self.assertEqual(out, [{'bill': 'HB 15', 'anchor': 0}])

    def test_enriched_speakers_rendered(self):
        roster = [{'people_id': 1, 'name': 'Robert McColley', 'first': 'Robert',
                   'last': 'McColley', 'middle': '', 'nickname': '', 'suffix': '',
                   'party': 'R', 'chamber': 'senate', 'district': 1}]
        d = {'program': {'id': 5, 'name': 'P5', 'release_date': '2026-06-10',
                         'duration': 200, 'series_id': 26, 'series_name': 'Senate',
                         'chamber': 'SENATE'},
             'captions': [],
             'sections': [{'start': 0, 'end': 200, 'type': 'Resolution', 'label': 'x',
                           'bills': [], 'persons': ['Robert McColley']}]}
        out = rt.render_program(d, roster=roster)
        self.assertIn('data-pagefind-filter="speaker">Robert McColley</span>', out)
        self.assertIn('R-1', out)  # party-district shown in the visible panel

    def test_video_link_present(self):
        self.assertIn('https://www.ohiochannel.org/program-details/208562', self.html)

    def test_chunk_links_seek_video(self):
        self.assertIn('program-details/208562?start=65', self.html)

    def test_find_widget_present_and_ignored_by_pagefind(self):
        self.assertIn('id="findInput"', self.html)
        self.assertIn('class="findbar" data-pagefind-ignore', self.html)
        self.assertIn("get('find')", self.html)


class RenderAllTests(unittest.TestCase):
    def test_render_all_writes_pages_and_index(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        progs = os.path.join(tmp, 'programs')
        out = os.path.join(tmp, 'site')
        dm.save_distilled(distilled_fixture(), progs)
        idx_path = os.path.join(tmp, 'programs_index.json')
        with open(idx_path, 'w') as f:
            json.dump([{'id': 208562, 'name': 'P', 'date': '2026-06-10', 'captions': True,
                        'series_name': 'House', 'chamber': 'HOUSE', 'is_floor': True,
                        'duration': 200, 'bills': [], 'speakers': []},
                       {'id': 9, 'name': 'No captions yet', 'date': '2026-06-11',
                        'captions': False, 'status': 'awaiting_captions'}], f)
        count = rt.render_all(progs, idx_path, out)
        self.assertEqual(count, 1)
        self.assertTrue(os.path.exists(os.path.join(out, '208562.html')))
        index_html = open(os.path.join(out, 'index.html'), encoding='utf-8').read()
        self.assertIn('captions not yet available', index_html)


if __name__ == '__main__':
    unittest.main()
