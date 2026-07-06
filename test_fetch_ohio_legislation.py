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
from datetime import datetime
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
            mock.patch.object(fetcher, 'CHANGES_OUTPUT', os.path.join(self.tmp, 'changes.json'), create=True),
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


class TestChangesFeed(TempDataDirTestCase):
    """The daily 'what moved' diff written to changes.json."""

    def write_bills(self, bills):
        with open(os.path.join(self.tmp, 'bills.json'), 'w') as f:
            json.dump(bills, f)

    def write_changes(self, entries):
        with open(os.path.join(self.tmp, 'changes.json'), 'w') as f:
            json.dump(entries, f)

    def read_changes(self):
        path = os.path.join(self.tmp, 'changes.json')
        self.assertTrue(os.path.exists(path), 'changes.json was not written')
        with open(path) as f:
            return json.load(f)

    def run_main_with(self, master, details_by_id, stored):
        self.write_hashes(stored)
        with mock.patch.object(fetcher, 'get_ohio_session_id', return_value=99), \
             mock.patch.object(fetcher, 'get_master_list', return_value=master), \
             mock.patch.object(fetcher, 'get_bill_details',
                               side_effect=lambda bid: details_by_id.get(str(bid))):
            fetcher.main()

    def existing_hb1(self, status='introduced', action='Introduced', date='2026-06-01'):
        return {
            'bill_id': 1, 'number': 'HB1', 'chamber': 'house',
            'title': 'Test bill HB1', 'description': '', 'status': status,
            'status_date': date, 'last_action': action, 'last_action_date': date,
            'sponsor': 'Unknown', 'committee': None, 'subject': 'general',
            'url': 'https://legiscan.com/OH/bill/HB1/2025',
        }

    def test_status_change_recorded_with_previous_status(self):
        self.write_bills([self.existing_hb1(status='introduced')])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 2  # engrossed -> passed-chamber
        updated['history'] = [{'action': 'Passed House', 'date': '2026-07-05'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        changes = self.read_changes()
        self.assertEqual(len(changes), 1)
        entry = changes[0]
        self.assertEqual(entry['number'], 'HB1')
        self.assertEqual(entry['prev_status'], 'introduced')
        self.assertEqual(entry['status'], 'passed-chamber')
        self.assertEqual(entry['last_action_date'], '2026-07-05')
        self.assertFalse(entry['is_new'])

    def test_brand_new_bill_recorded_as_new(self):
        self.write_bills([])
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': minimal_bill(1, 'HB1')},
            stored={},
        )
        changes = self.read_changes()
        self.assertEqual(len(changes), 1)
        self.assertTrue(changes[0]['is_new'])
        self.assertIsNone(changes[0]['prev_status'])

    def test_refetch_without_new_action_or_status_is_not_noise(self):
        # Hash changed (e.g. new bill text uploaded) but status and last
        # action are identical -> nothing a daily monitor needs to see
        self.write_bills([self.existing_hb1(status='introduced',
                                            action='Introduced', date='2026-06-01')])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 1
        updated['status_date'] = '2026-06-01'
        updated['history'] = [{'action': 'Introduced', 'date': '2026-06-01'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        changes = self.read_changes()
        self.assertEqual(changes, [])

    def test_mapping_only_status_change_is_noise(self):
        # Derived status changed (migration remap: passed -> became-law)
        # but the bill took no new action -> keep it out of the feed
        self.write_bills([self.existing_hb1(status='passed',
                                            action='Effective', date='2026-03-01')])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 4  # now maps to became-law
        updated['status_date'] = '2026-03-01'
        updated['history'] = [{'action': 'Effective', 'date': '2026-03-01'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        self.assertEqual(self.read_changes(), [])

    def test_real_enactment_with_new_action_is_recorded(self):
        self.write_bills([self.existing_hb1(status='passed',
                                            action='Sent to Governor', date='2026-06-20')])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 4
        updated['history'] = [{'action': 'Signed by Governor', 'date': '2026-07-05'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        changes = self.read_changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['status'], 'became-law')
        self.assertEqual(changes[0]['prev_status'], 'passed')

    def test_entries_older_than_14_days_are_pruned(self):
        self.write_bills([self.existing_hb1()])
        self.write_changes([
            {'run_date': '2026-01-01', 'number': 'SB99', 'is_new': False},
            {'run_date': datetime.now().strftime('%Y-%m-%d'), 'number': 'SB98', 'is_new': False},
        ])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 2
        updated['history'] = [{'action': 'Passed House', 'date': '2026-07-05'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        changes = self.read_changes()
        numbers = [c['number'] for c in changes]
        self.assertNotIn('SB99', numbers, 'stale entries must be pruned')
        self.assertIn('SB98', numbers, 'recent entries must survive')
        self.assertIn('HB1', numbers, 'new entries must be added')


class TestStatusMapping(unittest.TestCase):
    """Type-aware derivation of widget status from LegiScan status codes."""

    def formatted(self, number, status):
        b = minimal_bill(1, number)
        b['status'] = status
        return fetcher.format_bill_for_widget(b)

    def test_enrolled_bill_stays_passed_awaiting_governor(self):
        self.assertEqual(self.formatted('HB1', 3)['status'], 'passed')

    def test_status4_house_bill_became_law(self):
        self.assertEqual(self.formatted('HB1', 4)['status'], 'became-law')

    def test_status4_senate_bill_became_law(self):
        self.assertEqual(self.formatted('SB1', 4)['status'], 'became-law')

    def test_status4_joint_resolution_is_on_ballot(self):
        self.assertEqual(self.formatted('HJR2', 4)['status'], 'on-ballot')

    def test_status4_concurrent_resolution_stays_passed(self):
        self.assertEqual(self.formatted('SCR3', 4)['status'], 'passed')

    def test_status4_simple_resolution_stays_passed(self):
        self.assertEqual(self.formatted('HR4', 4)['status'], 'passed')

    def test_vetoed_unchanged(self):
        self.assertEqual(self.formatted('HB1', 5)['status'], 'vetoed')

    def test_raw_status_code_is_preserved(self):
        self.assertEqual(self.formatted('HB1', 4)['status_code'], 4)


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
