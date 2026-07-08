"""
Word-boundary topic matching + best-excerpt selection over distilled transcripts.
Whole-word only (never substring), so 'rent' never matches 'current'. Procedural
lines are excluded via transcript_slop.
"""
import html
import re

from transcript_slop import is_procedural


def compile_aliases(aliases):
    """Compile alias strings into whole-word, case-insensitive regexes."""
    return [re.compile(r'\b' + re.escape(a.lower()) + r'\b') for a in aliases]


def line_matches(text, patterns):
    """Number of distinct aliases that match this line (whole-word)."""
    low = (text or '').lower()
    return sum(1 for p in patterns if p.search(low))


def substantive_matches(distilled, patterns):
    """Count of non-procedural caption lines that match at least one alias."""
    n = 0
    for _, text in distilled['captions']:
        if is_procedural(text):
            continue
        if line_matches(text, patterns):
            n += 1
    return n


def best_excerpt(distilled, patterns, max_chars=240):
    """Highest-scoring non-procedural matching line + the following line, escaped.
    Score favors longer, more topic-dense lines: len(line) + 15 * alias_hits."""
    caps = distilled['captions']
    best_i, best_score = None, -1
    for i, (_, text) in enumerate(caps):
        if is_procedural(text):
            continue
        hits = line_matches(text, patterns)
        if not hits:
            continue
        score = len(text) + 15 * hits
        if score > best_score:
            best_score, best_i = score, i
    if best_i is None:
        return ''
    text = caps[best_i][1].strip()
    if best_i + 1 < len(caps):
        text = (text + ' ' + caps[best_i + 1][1].strip()).strip()
    return html.escape(text[:max_chars])
