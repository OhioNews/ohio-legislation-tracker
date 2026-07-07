"""
Builds the small derived JSON the answer page loads at startup:
  programs_index.json  — one line per meeting (captioned AND captionless)
  topics.json          — curated topics with counts and bill attribution
Single pass over the distilled archive; safe to rerun any time.
"""
import glob
import json
import os
from datetime import datetime, timedelta, timezone

import transcript_distill as dm

DATA_DIR = 'ohio_transcript_data'
PROGRAMS_DIR = os.path.join(DATA_DIR, 'programs')
STATE_FILE = os.path.join(DATA_DIR, 'transcript_state.json')
CURATED_FILE = os.path.join(DATA_DIR, 'topics_curated.json')
INDEX_OUT = os.path.join(DATA_DIR, 'programs_index.json')
TOPICS_OUT = os.path.join(DATA_DIR, 'topics.json')
RECENT_DAYS = 90
FLOOR_SERIES = (25, 26)


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def build_index_and_topics(programs_dir, state, curated, now=None):
    now = now or datetime.now(timezone.utc).date().isoformat()
    cutoff = (datetime.fromisoformat(now) - timedelta(days=RECENT_DAYS)).date().isoformat()

    topics = {t['slug']: {'name': t['name'], 'aliases': t['aliases'],
                          'meeting_count_90d': 0, 'program_ids': [], 'bills': set()}
              for t in curated}
    aliases_lower = {t['slug']: [a.lower() for a in t['aliases']] for t in curated}

    index = []
    for path in sorted(glob.glob(os.path.join(programs_dir, '*.json.gz'))):
        d = dm.load_distilled(path)
        p = d['program']
        bills = sorted({b for s in d['sections'] for b in s['bills']})
        speakers = sorted({n for s in d['sections'] for n in s['persons']})
        index.append({'id': p['id'], 'name': p['name'], 'date': p['release_date'],
                      'series_name': p['series_name'], 'chamber': p['chamber'],
                      'is_floor': p['series_id'] in FLOOR_SERIES,
                      'duration': p['duration'], 'bills': bills,
                      'speakers': speakers, 'captions': True})

        full_text = ' '.join(t for _, t in d['captions']).lower()
        for slug, alias_list in aliases_lower.items():
            if not any(a in full_text for a in alias_list):
                continue
            entry = topics[slug]
            entry['program_ids'].append(p['id'])
            if (p['release_date'] or '') >= cutoff:
                entry['meeting_count_90d'] += 1
            # bill attribution: alias must appear inside the bill's own section
            for s in d['sections']:
                if not s['bills']:
                    continue
                sec_text = ' '.join(t for st, t in d['captions']
                                    if s['start'] <= st < s['end']).lower()
                if any(a in sec_text for a in alias_list):
                    entry['bills'].update(s['bills'])

    archived_ids = {item['id'] for item in index}
    for pid, e in state.items():
        if int(pid) in archived_ids:
            continue
        if e.get('status') in ('awaiting_captions', 'captions_unavailable'):
            index.append({'id': int(pid), 'name': e.get('name', ''),
                          'date': e.get('release_date', ''),
                          'captions': False, 'status': e['status']})

    index.sort(key=lambda x: x.get('date') or '', reverse=True)
    for t in topics.values():
        t['bills'] = sorted(t['bills'])
    return index, topics


def main():
    state = _load(STATE_FILE, {})
    curated = _load(CURATED_FILE, [])
    index, topics = build_index_and_topics(PROGRAMS_DIR, state, curated)
    with open(INDEX_OUT, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False)
    with open(TOPICS_OUT, 'w', encoding='utf-8') as f:
        json.dump(topics, f, ensure_ascii=False)
    print(f"programs_index: {len(index)} entries; topics: {len(topics)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
