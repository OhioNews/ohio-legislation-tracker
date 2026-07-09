"""
Builds ohio_transcript_data/roster.json — the authoritative 136th GA member
list used to enrich transcript speaker names. Pulls from LegiScan
getSessionPeople. Reuses the API helpers in fetch_ohio_legislation.py.

Usage:  LEGISCAN_API_KEY=... python build_roster.py
"""
import json
import os
import re

import fetch_ohio_legislation as fetcher

ROSTER_OUT = os.path.join('ohio_transcript_data', 'roster.json')

_DISTRICT_RE = re.compile(r'(\d+)\s*$')


def _chamber_from_role(role):
    r = (role or '').strip().lower()
    if r.startswith('sen'):
        return 'senate'
    if r.startswith('rep'):
        return 'house'
    return None


def _district_num(district):
    m = _DISTRICT_RE.search(str(district or ''))
    return int(m.group(1)) if m else None


def parse_people(payload):
    """Turn a getSessionPeople response into roster member dicts."""
    if not payload or payload.get('status') != 'OK':
        return []
    people = (payload.get('sessionpeople') or {}).get('people') or []
    members = []
    for p in people:
        members.append({
            'people_id': p.get('people_id'),
            'name': p.get('name', ''),
            'first': p.get('first_name', ''),
            'last': p.get('last_name', ''),
            'middle': p.get('middle_name', ''),
            'nickname': p.get('nickname', ''),
            'suffix': p.get('suffix', ''),
            'party': p.get('party', ''),
            'chamber': _chamber_from_role(p.get('role')),
            'district': _district_num(p.get('district')),
            'role': p.get('role', ''),
        })
    return members


def build_roster(session_id, out_path=ROSTER_OUT):
    payload = fetcher.call_legiscan_api('getSessionPeople', {'id': session_id})
    members = parse_people(payload)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(members, f, ensure_ascii=False, indent=1)
    return members


def main():
    if not fetcher.LEGISCAN_API_KEY:
        print("✗ ERROR: LEGISCAN_API_KEY environment variable is not set!")
        return 1
    session_id = fetcher.get_ohio_session_id()
    if not session_id:
        print("✗ Could not resolve Ohio session id")
        return 1
    members = build_roster(session_id)
    print("roster.json: %d members" % len(members))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
