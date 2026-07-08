"""
Builds the small derived JSON the answer page loads at startup:
  programs_index.json  — one line per meeting (captioned AND captionless)
  topics.json          — curated topics: honest counts, hand-written brief, and a
                         substance-ranked list of meetings each with a best-quote
Whole-word matching + procedural-slop filtering (no substring false matches).
Single pass over the distilled archive; safe to rerun any time.
"""
import glob
import json
import os
from datetime import datetime, timedelta, timezone

import transcript_distill as dm
import transcript_relevance as rel
import transcript_slop as slop

DATA_DIR = 'ohio_transcript_data'
PROGRAMS_DIR = os.path.join(DATA_DIR, 'programs')
STATE_FILE = os.path.join(DATA_DIR, 'transcript_state.json')
CURATED_FILE = os.path.join(DATA_DIR, 'topics_curated.json')
INDEX_OUT = os.path.join(DATA_DIR, 'programs_index.json')
TOPICS_OUT = os.path.join(DATA_DIR, 'topics.json')
RECENT_DAYS = 90
FLOOR_SERIES = (25, 26)
MIN_TOPIC_MATCHES = 8


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def build_index_and_topics(programs_dir, state, curated, now=None):
    now = now or datetime.now(timezone.utc).date().isoformat()
    cutoff = (datetime.fromisoformat(now) - timedelta(days=RECENT_DAYS)).date().isoformat()

    compiled = {t['slug']: rel.compile_aliases(t['aliases']) for t in curated}
    topics = {t['slug']: {'name': t['name'], 'brief': t.get('brief', ''),
                          'aliases': t['aliases'], 'total': 0, 'recent': 0,
                          'bills': set(), 'meetings': []} for t in curated}

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

        for slug, patterns in compiled.items():
            matches = rel.substantive_matches(d, patterns)
            if matches < MIN_TOPIC_MATCHES:
                continue
            entry = topics[slug]
            entry['total'] += 1
            if (p['release_date'] or '') >= cutoff:
                entry['recent'] += 1
            # bills whose own marker-section carries a substantive (non-procedural) topic hit
            mtg_bills = []
            for s in d['sections']:
                if not s['bills']:
                    continue
                for st, text in d['captions']:
                    if s['start'] <= st < s['end'] and not slop.is_procedural(text) \
                            and rel.line_matches(text, patterns):
                        mtg_bills.extend(s['bills'])
                        break
            mtg_bills = sorted(set(mtg_bills))
            entry['bills'].update(mtg_bills)
            entry['meetings'].append({
                'id': p['id'], 'name': p['name'], 'date': p['release_date'],
                'series_name': p['series_name'], 'chamber': p['chamber'],
                'is_floor': p['series_id'] in FLOOR_SERIES,
                'matches': matches, 'excerpt': rel.best_excerpt(d, patterns),
                'bills': mtg_bills,
            })

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
        t['meetings'].sort(key=lambda m: (m['matches'], m['date'] or ''), reverse=True)
    return index, topics


def main():
    state = _load(STATE_FILE, {})
    curated = _load(CURATED_FILE, [])
    index, topics = build_index_and_topics(PROGRAMS_DIR, state, curated)
    with open(INDEX_OUT, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False)
    with open(TOPICS_OUT, 'w', encoding='utf-8') as f:
        json.dump(topics, f, ensure_ascii=False)
    print("programs_index: %d entries; topics: %d" % (len(index), len(topics)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
