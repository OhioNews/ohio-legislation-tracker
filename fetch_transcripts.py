"""
Statehouse Transcripts fetcher - Signal Ohio

Nightly: archives Ohio Channel captions+markers for new legislative programs
(136th GA window) into ohio_transcript_data/programs/. Append-only; existing
distilled files are never rewritten. Captionless programs are rechecked for
CAPTION_RECHECK_DAYS, then marked captions_unavailable (still listed in UI).

Usage:
  python fetch_transcripts.py                 # nightly incremental
  python fetch_transcripts.py --backfill      # paginate to GA start (one-time)
  python fetch_transcripts.py --limit 60      # cap programs processed (validation)
  python fetch_transcripts.py --series 26     # single series
"""
import argparse
import json
import os
from datetime import datetime, timezone

import ohiochannel_api as api
import transcript_distill as dm

DATA_DIR = 'ohio_transcript_data'
PROGRAMS_DIR = os.path.join(DATA_DIR, 'programs')
STATE_FILE = os.path.join(DATA_DIR, 'transcript_state.json')
META_FILE = os.path.join(DATA_DIR, 'transcripts_meta.json')
SERIES_CONFIG = os.path.join(DATA_DIR, 'transcript_series.json')
CAPTION_RECHECK_DAYS = 14
PAGE_SIZE = 50


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _trim_program(program):
    series = program.get('series') or {}
    return {'id': program['id'], 'fullName': program.get('fullName', ''),
            'releaseDate': program.get('releaseDate'), 'duration': program.get('duration'),
            'series': {'id': series.get('id'), 'name': series.get('name', ''),
                       'chamber': series.get('chamber')}}


def discover_programs(series_entry, ga_start, state, backfill):
    """New programs for one series, newest first.

    Non-backfill reads page 1 and stops at the GA window edge or the first
    already-archived program (watermark). Backfill paginates the whole series,
    skipping known programs, until the GA window edge.
    """
    found = []
    start = 1
    while True:
        resp = api.list_programs(series_entry['id'], start=start, page_size=PAGE_SIZE)
        records = resp.get('records') or []
        if not records:
            break
        stop = False
        for p in records:
            rd = (p.get('releaseDate') or '')[:10]
            if rd and rd < ga_start:
                stop = True
                break
            pid = str(p['id'])
            if pid in state:
                if state[pid].get('status') == 'archived' and not backfill:
                    stop = True
                    break
                continue  # awaiting/unavailable handled by recheck pass; known-archived skipped
            found.append(p)
        if stop or not backfill:
            break
        start += PAGE_SIZE
    return found


def process_program(program, state, today=None):
    """Fetch captions (+markers), distill and archive. Returns resulting status."""
    pid = str(program['id'])
    today = today or datetime.now(timezone.utc).date().isoformat()
    captions = api.get_captions(program['id'])
    if not captions:
        first = state.get(pid, {}).get('first_seen', today)
        age = (datetime.fromisoformat(today) - datetime.fromisoformat(first)).days
        status = 'captions_unavailable' if age > CAPTION_RECHECK_DAYS else 'awaiting_captions'
        entry = {'status': status, 'first_seen': first,
                 'release_date': (program.get('releaseDate') or '')[:10],
                 'name': program.get('fullName', '')}
        if status == 'awaiting_captions':
            entry['program'] = _trim_program(program)
        state[pid] = entry
        return status
    markers = api.get_markers(program['id'])
    d = dm.distill(program, captions, markers)
    dm.save_distilled(d, PROGRAMS_DIR)
    state[pid] = {'status': 'archived',
                  'release_date': d['program']['release_date'],
                  'name': d['program']['name']}
    return 'archived'


def main(argv=None):
    ap = argparse.ArgumentParser(description='Archive Ohio Channel transcripts')
    ap.add_argument('--backfill', action='store_true')
    ap.add_argument('--series', type=int, default=None)
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args(argv)

    cfg = load_json(SERIES_CONFIG, None)
    if not cfg:
        print(f'ERROR: missing {SERIES_CONFIG} — run build_series_config.py first')
        return 1
    state = load_json(STATE_FILE, {})
    counts = {'archived': 0, 'awaiting_captions': 0, 'captions_unavailable': 0}

    # Recheck pass: programs still waiting on late captions
    for pid in list(state):
        entry = state[pid]
        if entry.get('status') == 'awaiting_captions' and entry.get('program'):
            counts[process_program(entry['program'], state)] += 1

    processed = 0
    series_list = [s for s in cfg['series'] if args.series is None or s['id'] == args.series]
    for s in series_list:
        if args.limit is not None and processed >= args.limit:
            break
        for p in discover_programs(s, cfg['ga_start_date'], state, args.backfill):
            if args.limit is not None and processed >= args.limit:
                break
            counts[process_program(p, state)] += 1
            processed += 1

    save_json(STATE_FILE, state)
    save_json(META_FILE, {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'archived_total': sum(1 for e in state.values() if e.get('status') == 'archived'),
        'last_run': counts,
    })
    print(f"Done: {counts}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
