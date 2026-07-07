"""
Tests for ohiochannel_api.py. Run: python -m unittest test_ohiochannel_api -v
Mocks urllib at the module boundary; no network.
"""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ohiochannel_api as api


def fake_response(payload):
    return io.BytesIO(json.dumps(payload).encode('utf-8'))


class FetchJsonTests(unittest.TestCase):
    def setUp(self):
        # neutralize throttle sleeps in tests
        self.sleep_patch = mock.patch('ohiochannel_api.time.sleep')
        self.mock_sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def test_sends_identifying_user_agent(self):
        captured = {}
        def fake_urlopen(req, timeout=None, context=None):
            captured['ua'] = req.get_header('User-agent')
            return fake_response({'ok': True})
        with mock.patch('ohiochannel_api.urllib.request.urlopen', fake_urlopen):
            api.fetch_json('https://example.test/x')
        self.assertEqual(captured['ua'], 'ohio-legislation-tracker (scott@signalohio.org)')

    def test_retries_then_raises(self):
        def always_fail(req, timeout=None, context=None):
            raise OSError('boom')
        with mock.patch('ohiochannel_api.urllib.request.urlopen', always_fail):
            with self.assertRaises(RuntimeError):
                api.fetch_json('https://example.test/x')

    def test_recovers_on_second_attempt(self):
        calls = {'n': 0}
        def flaky(req, timeout=None, context=None):
            calls['n'] += 1
            if calls['n'] == 1:
                raise OSError('boom')
            return fake_response({'ok': True})
        with mock.patch('ohiochannel_api.urllib.request.urlopen', flaky):
            self.assertEqual(api.fetch_json('https://example.test/x'), {'ok': True})
        self.assertEqual(calls['n'], 2)


class EndpointTests(unittest.TestCase):
    def test_list_programs_builds_get_query(self):
        with mock.patch.object(api, 'fetch_json', return_value={'records': [], 'recordCount': 0}) as fj:
            api.list_programs(26, start=51, page_size=50)
        url = fj.call_args[0][0]
        self.assertIn('/programming/programs?', url)
        self.assertIn('series=26', url)
        self.assertIn('start=51', url)
        self.assertIn('sort=releaseDate', url)

    def test_get_captions_unwraps_records(self):
        with mock.patch.object(api, 'fetch_json',
                               return_value={'records': [{'startTime': 1.0, 'text': 'hi'}]}):
            recs = api.get_captions(208562)
        self.assertEqual(recs, [{'startTime': 1.0, 'text': 'hi'}])

    def test_get_markers_handles_empty(self):
        with mock.patch.object(api, 'fetch_json', return_value={'records': [], 'recordCount': 0}):
            self.assertEqual(api.get_markers(208788), [])


if __name__ == '__main__':
    unittest.main()
