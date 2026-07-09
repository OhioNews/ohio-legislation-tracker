"""
Enriches transcript speaker names against the 136th GA roster and scans each
program's introduction window (title-anchored) for members the markers missed.
Shared by build_transcript_derived.py and render_transcripts.py.
"""
import re

import roster_match as rm

INTRO_FALLBACK_SECONDS = 600

# Section types that make up the opening of a session/hearing.
_INTRO_KEYWORDS = ('convene', 'invocation', 'swearing', 'roll call',
                   'recognition', 'personal privilege')

# Title-anchored patterns. Each captures a name-ish token to hand to match_name.
_NAME = r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)?)"
_PATTERNS = [
    re.compile(r'\b(?:Senator|Representative|Sen\.|Rep\.)\s+' + _NAME),
    re.compile(r'\bgentle(?:man|lady|men|women)\s+from\b[^.]*?'
               r"(?:Mr\.|Mrs\.|Ms\.|Miss)\s+" + _NAME),
    re.compile(r"^" + _NAME + r"[:,]\s*(?:present|here)\b", re.IGNORECASE),
]


def _is_intro_type(section_type):
    t = (section_type or '').lower()
    return any(k in t for k in _INTRO_KEYWORDS)


def _intro_window_end(distilled):
    sections = distilled.get('sections') or []
    intro = [s for s in sections if _is_intro_type(s.get('type'))]
    if intro:
        return max(s.get('end') or 0 for s in intro)
    return INTRO_FALLBACK_SECONDS


def scan_intro_window(distilled, roster):
    if not roster:
        return []
    chamber = distilled.get('program', {}).get('chamber')
    window_end = _intro_window_end(distilled)
    found = {}
    for start, text in distilled.get('captions') or []:
        if start >= window_end:
            continue
        for pat in _PATTERNS:
            for m in pat.finditer(text):
                member = rm.match_name(m.group(1), chamber, roster)
                if member:
                    found[member['people_id']] = member
    return list(found.values())


def _entry(member, name, source):
    return {'name': member['name'] if member else name,
            'party': member['party'] if member else None,
            'district': member['district'] if member else None,
            'chamber': member['chamber'] if member else None,
            'source': source, 'matched': bool(member)}


def enrich_speakers(distilled, roster):
    chamber = distilled.get('program', {}).get('chamber')
    marker_names = []
    for s in distilled.get('sections') or []:
        for n in s.get('persons') or []:
            if n not in marker_names:
                marker_names.append(n)

    scanned = {m['people_id']: m for m in scan_intro_window(distilled, roster)}

    entries = {}
    order = []
    for name in marker_names:
        member = rm.match_name(name, chamber, roster)
        if member and member['people_id'] in scanned:
            e = _entry(member, name, 'both')
            scanned.pop(member['people_id'])
            key = member['name']
        elif member:
            e = _entry(member, name, 'marker')
            key = member['name']
        else:
            e = _entry(None, name, 'marker')
            key = name
        if key not in entries:
            entries[key] = e
            order.append(key)

    for member in scanned.values():
        key = member['name']
        if key not in entries:
            entries[key] = _entry(member, key, 'intro-scan')
            order.append(key)

    return sorted((entries[k] for k in order), key=lambda x: x['name'])
