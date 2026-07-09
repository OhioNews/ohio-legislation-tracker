"""
Resolves a transcript name string (from a marker or an intro-window scan) to a
136th GA roster member. Chamber-constrained: an explicit full-name match wins
regardless of chamber; a bare last name only resolves when unique within the
program's chamber.
"""
import json
import os
import re

_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
_TITLES = {'sen', 'senator', 'rep', 'representative', 'mr', 'mrs', 'ms', 'miss',
           'dr', 'pastor', 'the'}


def load_roster(path=os.path.join('ohio_transcript_data', 'roster.json')):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _clean(tok):
    return re.sub(r'[.,]', '', tok or '').strip().lower()


def _tokens(raw):
    """Lowercased name tokens with titles, suffixes, and lone initials removed."""
    out = []
    for t in re.split(r'\s+', (raw or '').strip()):
        c = _clean(t)
        if not c or c in _TITLES or c in _SUFFIXES:
            continue
        if len(c) == 1:  # lone middle/first initial
            continue
        out.append(c)
    return out


def _norm_chamber(chamber):
    c = (chamber or '').strip().lower()
    return c if c in ('house', 'senate') else None


def match_name(raw, chamber, roster):
    if not roster:
        return None
    toks = _tokens(raw)
    if not toks:
        return None
    last = toks[-1]
    firsts = set(toks[:-1])
    ch = _norm_chamber(chamber)

    same_last = [m for m in roster if _clean(m.get('last')) == last]
    if not same_last:
        return None

    # Full-name match (first or nickname), chamber-agnostic; wins over chamber.
    if firsts:
        full = [m for m in same_last
                if _clean(m.get('first')) in firsts or _clean(m.get('nickname')) in firsts]
        if len(full) == 1:
            return full[0]
        if len(full) > 1:  # disambiguate a true full-name tie by chamber
            in_ch = [m for m in full if m.get('chamber') == ch]
            return in_ch[0] if len(in_ch) == 1 else None

    # Bare last name: only if unique within the given chamber.
    if ch:
        in_ch = [m for m in same_last if m.get('chamber') == ch]
        if len(in_ch) == 1:
            return in_ch[0]
        return None
    return same_last[0] if len(same_last) == 1 else None
