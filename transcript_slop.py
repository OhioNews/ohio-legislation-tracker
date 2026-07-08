"""
Procedural-slop detection for Statehouse transcript captions.
A "procedural" line — roll-call/vote tally, gavel/procedure boilerplate, or
trivially short — is excluded from substance scoring and never chosen as an
excerpt. The point is to keep substance (testimony, debate, argument) and drop
the mechanics of running a meeting.
"""
import re

VOTE_TOKEN = re.compile(r'\b(yes|no|aye|nay|present|absent)\b', re.I)

# Gavel / procedure phrases. A line whose content is essentially one of these
# (nothing substantive beyond it) is procedural.
PROCEDURAL_PHRASES = [
    'call the roll', 'without objection', 'seeing none', 'hearing none',
    'the ayes have it', 'motion carries', 'come to order', 'please rise',
    'pledge of allegiance', 'the clerk will', 'point of order',
    'chair recognizes', 'yields back', 'title agreed to', 'third reading',
    'second reading', 'minutes approved', 'sponsor testimony',
    'proponent testimony', 'opponent testimony', 'written testimony',
    'happy to answer', 'thank you for the opportunity',
]
_PHRASE_RES = [re.compile(re.escape(p), re.I) for p in PROCEDURAL_PHRASES]

# One capitalized 1-2 word proper-noun token (a roll-call name like "Kaler" or
# "Bryant Bailey"); "Yes"/"No" also match, which is fine for name-list runs.
_NAME_TOKEN = re.compile(r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+)?$')

MIN_SUBSTANCE_CHARS = 25
PHRASE_RESIDUAL_MAX = 15


def _looks_like_roll_call(line):
    if len(VOTE_TOKEN.findall(line)) >= 3:
        return True
    parts = [p.strip() for p in re.split(r'[.,;]', line) if p.strip()]
    if len(parts) >= 4:
        namey = sum(1 for p in parts if _NAME_TOKEN.match(p))
        if namey >= 4 and namey / len(parts) >= 0.6:
            return True
    return False


def is_procedural(line):
    """True if the caption line is procedural (roll-call, gavel phrase, trivial)."""
    s = (line or '').strip()
    if len(s) < MIN_SUBSTANCE_CHARS:
        return True
    if _looks_like_roll_call(s):
        return True
    for rx in _PHRASE_RES:
        m = rx.search(s)
        if m:
            residual = (s[:m.start()] + s[m.end():]).strip()
            if len(residual) <= PHRASE_RESIDUAL_MAX:
                return True
    return False
