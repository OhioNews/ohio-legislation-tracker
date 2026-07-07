"""
Distills raw Ohio Channel caption + marker JSON into the compact archived
format (one gzipped JSON per program). Raw API responses are not kept.
"""
import gzip
import json
import os

LEG_ABBREV = {
    'HOUSE_BILL': 'HB', 'SENATE_BILL': 'SB',
    'HOUSE_JOINT_RESOLUTION': 'HJR', 'SENATE_JOINT_RESOLUTION': 'SJR',
    'HOUSE_CONCURRENT_RESOLUTION': 'HCR', 'SENATE_CONCURRENT_RESOLUTION': 'SCR',
    'HOUSE_RESOLUTION': 'HR', 'SENATE_RESOLUTION': 'SR',
}


def bill_label(marker):
    t = marker.get('legislationType')
    n = marker.get('legislationNumber')
    if not t or not n:
        return None
    return f"{LEG_ABBREV.get(t, t)} {n}"


def _collect_descendants(marker, persons, bills):
    for c in marker.get('children') or []:
        p = c.get('person')
        if p and p.get('displayName'):
            persons.append(p['displayName'])
        b = bill_label(c)
        if b:
            bills.append(b)
        _collect_descendants(c, persons, bills)


def build_sections(markers, end_time):
    tops = sorted(markers or [], key=lambda m: m.get('time') or 0)
    sections = []
    for i, m in enumerate(tops):
        start = m.get('time') or 0
        end = (tops[i + 1].get('time') or end_time) if i + 1 < len(tops) else end_time
        persons, bills = [], []
        p = m.get('person')
        if p and p.get('displayName'):
            persons.append(p['displayName'])
        b = bill_label(m)
        if b:
            bills.append(b)
        _collect_descendants(m, persons, bills)
        persons = list(dict.fromkeys(persons))
        bills = list(dict.fromkeys(bills))
        mtype = (m.get('markerType') or {}).get('name') or ''
        desc = (m.get('description') or '').strip()
        label_parts = [x for x in (mtype, bills[0] if bills else None,
                                   ', '.join(persons) or None, desc or None) if x]
        sections.append({'start': start, 'end': end, 'type': mtype,
                         'label': ' · '.join(label_parts) or 'Segment',
                         'bills': bills, 'persons': persons})
    if not sections:
        sections = [{'start': 0, 'end': end_time, 'type': '',
                     'label': 'Full session', 'bills': [], 'persons': []}]
    return sections


def section_for(sections, t):
    """Section containing time t. Starts are inclusive: t == boundary -> later section."""
    current = sections[0] if sections else None
    for s in sections:
        if s['start'] <= t:
            current = s
        else:
            break
    return current


def distill(program, captions, markers):
    cap = sorted(
        [[round(float(c['startTime']), 1), c['text'].strip()]
         for c in captions if c.get('text') and c.get('startTime') is not None],
        key=lambda x: x[0],
    )
    end_time = program.get('duration') or (cap[-1][0] + 10 if cap else 0)
    series = program.get('series') or {}
    return {
        'program': {
            'id': program['id'],
            'name': program.get('fullName') or program.get('name', ''),
            'release_date': (program.get('releaseDate') or '')[:10],
            'duration': program.get('duration'),
            'series_id': series.get('id'),
            'series_name': series.get('name', ''),
            'chamber': series.get('chamber'),
        },
        'captions': cap,
        'sections': build_sections(markers, end_time),
    }


def distilled_path(out_dir, program_id):
    return os.path.join(out_dir, f"{program_id}.json.gz")


def save_distilled(d, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = distilled_path(out_dir, d['program']['id'])
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(d, f, separators=(',', ':'), ensure_ascii=False)
    return path


def load_distilled(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return json.load(f)
