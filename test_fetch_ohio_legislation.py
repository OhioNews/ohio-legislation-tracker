"""
Tests for fetch_ohio_legislation.py hardening behaviors.

Run with:  python -m unittest test_fetch_ohio_legislation -v

These tests monkeypatch the LegiScan API boundary so they run offline
with no API key.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_ohio_legislation as fetcher


def minimal_bill(bill_id, number):
    """Smallest bill dict format_bill_for_widget accepts."""
    return {
        'bill_id': bill_id,
        'bill_number': number,
        'title': f'Test bill {number}',
        'description': '',
        'status': 1,
        'status_date': '2026-01-01',
        'url': f'https://legiscan.com/OH/bill/{number}/2025',
    }


class TempDataDirTestCase(unittest.TestCase):
    """Redirects the fetcher's output files into a temp directory."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [
            mock.patch.object(fetcher, 'OUTPUT_DIR', self.tmp),
            mock.patch.object(fetcher, 'BILLS_OUTPUT', os.path.join(self.tmp, 'bills.json')),
            mock.patch.object(fetcher, 'HEARINGS_OUTPUT', os.path.join(self.tmp, 'hearings.json')),
            mock.patch.object(fetcher, 'HASH_STORAGE', os.path.join(self.tmp, 'bill_hashes.json')),
            mock.patch.object(fetcher, 'META_OUTPUT', os.path.join(self.tmp, 'meta.json')),
            mock.patch.object(fetcher, 'LEGISCAN_API_KEY', 'test-key'),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def write_hashes(self, hashes):
        with open(os.path.join(self.tmp, 'bill_hashes.json'), 'w') as f:
            json.dump(hashes, f)

    def read_hashes(self):
        with open(os.path.join(self.tmp, 'bill_hashes.json')) as f:
            return json.load(f)

    def read_meta(self):
        path = os.path.join(self.tmp, 'meta.json')
        self.assertTrue(os.path.exists(path), 'meta.json was not written')
        with open(path) as f:
            return json.load(f)


class TestFatalErrorsExitNonzero(TempDataDirTestCase):

    def test_missing_api_key_exits_nonzero(self):
        with mock.patch.object(fetcher, 'LEGISCAN_API_KEY', ''):
            with self.assertRaises(SystemExit) as cm:
                fetcher.main()
        self.assertNotEqual(cm.exception.code, 0)

    def test_session_lookup_failure_exits_nonzero(self):
        with mock.patch.object(fetcher, 'call_legiscan_api', return_value=None):
            with self.assertRaises(SystemExit) as cm:
                fetcher.main()
        self.assertNotEqual(cm.exception.code, 0)

    def test_master_list_failure_exits_nonzero(self):
        with mock.patch.object(fetcher, 'get_ohio_session_id', return_value=99), \
             mock.patch.object(fetcher, 'get_master_list', return_value={}):
            with self.assertRaises(SystemExit) as cm:
                fetcher.main()
        self.assertNotEqual(cm.exception.code, 0)

    def test_all_bill_fetches_failing_exits_nonzero(self):
        self.write_hashes({})
        master = {'0': {'bill_id': 1, 'change_hash': 'a1'}}
        with mock.patch.object(fetcher, 'get_ohio_session_id', return_value=99), \
             mock.patch.object(fetcher, 'get_master_list', return_value=master), \
             mock.patch.object(fetcher, 'get_bill_details', return_value=None):
            with self.assertRaises(SystemExit) as cm:
                fetcher.main()
        self.assertNotEqual(cm.exception.code, 0)


class TestFailedFetchHashPreservation(TempDataDirTestCase):

    def run_main_with(self, master, details_by_id, stored):
        self.write_hashes(stored)
        with mock.patch.object(fetcher, 'get_ohio_session_id', return_value=99), \
             mock.patch.object(fetcher, 'get_master_list', return_value=master), \
             mock.patch.object(fetcher, 'get_bill_details',
                               side_effect=lambda bid: details_by_id.get(str(bid))):
            fetcher.main()

    def test_failed_fetch_keeps_old_hash_so_bill_retries_next_run(self):
        master = {
            '0': {'bill_id': 1, 'change_hash': 'a2'},
            '1': {'bill_id': 2, 'change_hash': 'b2'},
        }
        details = {'1': minimal_bill(1, 'HB1')}  # bill 2 fetch fails
        self.run_main_with(master, details, stored={'1': 'a1', '2': 'b1'})

        hashes = self.read_hashes()
        self.assertEqual(hashes['1'], 'a2', 'successful fetch should advance hash')
        self.assertEqual(hashes['2'], 'b1', 'failed fetch must keep old hash to retry')

    def test_failed_fetch_of_brand_new_bill_leaves_no_hash(self):
        master = {
            '0': {'bill_id': 1, 'change_hash': 'a2'},
            '1': {'bill_id': 2, 'change_hash': 'b2'},
        }
        details = {'1': minimal_bill(1, 'HB1')}  # new bill 2 fetch fails
        self.run_main_with(master, details, stored={'1': 'a1'})

        hashes = self.read_hashes()
        self.assertNotIn('2', hashes, 'failed new bill must stay unknown so it retries')


class TestMetaFreshnessStamp(TempDataDirTestCase):

    def test_meta_written_when_nothing_changed(self):
        master = {'0': {'bill_id': 1, 'change_hash': 'a1'}}
        self.write_hashes({'1': 'a1'})  # up to date -> early "no changes" path
        with mock.patch.object(fetcher, 'get_ohio_session_id', return_value=99), \
             mock.patch.object(fetcher, 'get_master_list', return_value=master):
            fetcher.main()

        meta = self.read_meta()
        self.assertIn('last_updated', meta)
        self.assertEqual(meta['updated_last_run'], 0)

    def test_meta_written_after_successful_update(self):
        master = {'0': {'bill_id': 1, 'change_hash': 'a2'}}
        self.write_hashes({})
        details = {'1': minimal_bill(1, 'HB1')}
        with mock.patch.object(fetcher, 'get_ohio_session_id', return_value=99), \
             mock.patch.object(fetcher, 'get_master_list', return_value=master), \
             mock.patch.object(fetcher, 'get_bill_details',
                               side_effect=lambda bid: details.get(str(bid))):
            fetcher.main()

        meta = self.read_meta()
        self.assertIn('last_updated', meta)
        self.assertEqual(meta['bill_count'], 1)
        self.assertEqual(meta['updated_last_run'], 1)


class TestApiCallTimeout(unittest.TestCase):

    def test_api_calls_use_a_timeout(self):
        with mock.patch.object(fetcher, 'LEGISCAN_API_KEY', 'test-key'), \
             mock.patch.object(fetcher.requests, 'get') as fake_get:
            fake_get.return_value.raise_for_status.return_value = None
            fake_get.return_value.json.return_value = {'status': 'OK'}
            fetcher.call_legiscan_api('getSessionList')
        self.assertIn('timeout', fake_get.call_args.kwargs,
                      'requests.get must set a timeout or a hung API call hangs the workflow')


if __name__ == '__main__':
    unittest.main(verbosity=2)
