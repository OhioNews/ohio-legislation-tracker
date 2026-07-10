import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bill_refs as br


def prog(caps):
    return {'captions': [[t, s] for t, s in caps], 'sections': [], 'program': {}}


class TestScanBillRefs(unittest.TestCase):
    def test_spelled_out_forms(self):
        out = br.scan_bill_refs(prog([
            (10.0, 'We now take up House Bill 15 for consideration.'),
            (20.0, 'Senate Bill 162 is also on the calendar.'),
        ]))
        self.assertEqual({r['bill'] for r in out}, {'HB 15', 'SB 162'})

    def test_abbreviated_forms(self):
        out = br.scan_bill_refs(prog([
            (5.0, 'Testimony on H.B. 15 begins.'),
            (6.0, 'and S.B. 162 follows, plus SB162 later.'),
        ]))
        self.assertEqual({r['bill'] for r in out}, {'HB 15', 'SB 162'})

    def test_resolutions(self):
        out = br.scan_bill_refs(prog([
            (1.0, 'Senate Joint Resolution 2 and House Resolution 4 adopted.'),
            (2.0, 'House Concurrent Resolution 3 referred.'),
        ]))
        self.assertEqual({r['bill'] for r in out}, {'SJR 2', 'HR 4', 'HCR 3'})

    def test_substitute_prefix_stripped(self):
        out = br.scan_bill_refs(prog([(3.0, 'Amended Substitute Senate Bill 1 passes.')]))
        self.assertEqual([r['bill'] for r in out], ['SB 1'])

    def test_false_positives_rejected(self):
        out = br.scan_bill_refs(prog([
            (1.0, 'pursuant to article two, section 8 of the Ohio Constitution'),
            (2.0, 'in the year 2026 we met'),
        ]))
        self.assertEqual(out, [])

    def test_earliest_time_per_bill(self):
        out = br.scan_bill_refs(prog([
            (30.0, 'House Bill 15 again'),
            (10.0, 'House Bill 15 first'),
        ]))
        self.assertEqual(out, [{'bill': 'HB 15', 'time': 10.0}])


if __name__ == '__main__':
    unittest.main()
