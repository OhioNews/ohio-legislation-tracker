"""
Scans transcript captions for spoken/written bill references and normalizes
them to the tracker's canonical "<PREFIX> <NUM>" form, each with the earliest
timestamp it was mentioned. First-pass heuristic; tuned over time.
"""
import re

# chamber word + type word -> prefix
_TYPE = {
    'bill': 'B',
    'joint resolution': 'JR',
    'concurrent resolution': 'CR',
    'resolution': 'R',
}
_CHAMBER = {'house': 'H', 'senate': 'S'}

# "Senate Joint Resolution 2", "House Bill 15" (optional "No.")
_SPELLED = re.compile(
    r'\b(House|Senate)\s+'
    r'(Joint Resolution|Concurrent Resolution|Resolution|Bill)\s+'
    r'(?:No\.?\s*)?(\d{1,4})\b', re.IGNORECASE)

# "H.B. 15", "S.J.R. 2", "SB162", "H. R. 4"
_ABBREV = re.compile(
    r'\b([HS])\.?\s*(B|J\.?\s*R|C\.?\s*R|R)\.?\s*(\d{1,4})\b')

_ABBREV_TYPE = {'B': 'B', 'JR': 'JR', 'CR': 'CR', 'R': 'R'}


def _canon_spelled(chamber, typ, num):
    return f"{_CHAMBER[chamber.lower()]}{_TYPE[typ.lower()]} {int(num)}"


def _canon_abbrev(ch, typ, num):
    t = re.sub(r'[.\s]', '', typ).upper()  # "J R" / "J.R" -> "JR"
    t = _ABBREV_TYPE.get(t)
    if not t:
        return None
    return f"{ch.upper()}{t} {int(num)}"


def scan_bill_refs(distilled):
    seen = {}
    order = []
    for time, text in distilled.get('captions') or []:
        found = []
        for m in _SPELLED.finditer(text):
            found.append(_canon_spelled(m.group(1), m.group(2), m.group(3)))
        for m in _ABBREV.finditer(text):
            c = _canon_abbrev(m.group(1), m.group(2), m.group(3))
            if c:
                found.append(c)
        for bill in found:
            if bill not in seen:
                seen[bill] = time
                order.append(bill)
            elif time < seen[bill]:
                seen[bill] = time
    return [{'bill': b, 'time': seen[b]} for b in order]
