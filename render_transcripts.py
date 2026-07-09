"""
Renders distilled transcripts into static HTML pages for Pagefind indexing
and human reading. Every API-sourced string is escaped. Pages are built into
_site/ at deploy time — never committed.
"""
import glob
import html
import json
import os

import transcript_distill as dm
import bill_refs as brefs

CHUNK_SECONDS = 60
FLOOR_SERIES = (25, 26)
# The player reads ?start={seconds} from the URL (verified in the site's own
# share/embed code, July 2026) — links can seek straight to a moment.
VIDEO_URL_TEMPLATE = 'https://www.ohiochannel.org/program-details/{pid}'
VIDEO_TIME_PARAM = '?start={seconds}'
FOOTER_TEXT = ('Transcripts from Ohio Channel closed captions; not an official record. '
               'Verify against video before quoting.')
SPEAKER_NOTE = 'Speaker names available for floor sessions only.'

PAGE_CSS = """
body{font-family:Georgia,serif;max-width:46rem;margin:0 auto;padding:1rem;line-height:1.55;color:#222}
h1{font-size:1.4rem;line-height:1.3} h2{font-size:1.05rem;background:#f3f0e8;padding:.4rem .6rem;margin-top:2rem}
h3{font-size:.8rem;color:#8a8a8a;font-weight:normal;margin:1.2rem 0 .2rem;font-family:system-ui,sans-serif}
h3 a{color:#8a8a8a;text-decoration:none} h3 a:hover{text-decoration:underline}
p{margin:.3rem 0} .meta{font-family:system-ui,sans-serif;font-size:.85rem;color:#555}
.footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #ddd;font-family:system-ui,sans-serif;font-size:.8rem;color:#777}
.watch{font-family:system-ui,sans-serif;font-size:.8rem} :target{background:#fff7d6}
.bills{margin:1.2rem 0;font-family:system-ui,sans-serif;font-size:.9rem}
.bills h2{font-size:.95rem} .bills ul{list-style:none;padding:0;margin:.4rem 0}
.bills li{padding:.15rem 0} .bills .track{color:#555;font-size:.8rem}
"""


def hms(t):
    t = int(t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _chunks(captions, start, end):
    """Group a section's caption lines into CHUNK_SECONDS buckets."""
    lines = [c for c in captions if start <= c[0] < end]
    chunks = []
    for t, text in lines:
        if not chunks or t >= chunks[-1]['start'] + CHUNK_SECONDS:
            chunks.append({'start': t, 'lines': []})
        chunks[-1]['lines'].append(text)
    return chunks


def bills_in_context(d, known_bills=None):
    """The bills this meeting was about — marker agenda bills plus bills spoken
    in the captions — each resolved to the section anchor where it comes up."""
    sections = d.get('sections') or []
    times = {}  # canonical bill -> earliest time
    for s in sections:
        for b in s.get('bills') or []:
            t = s.get('start') or 0
            if b not in times or t < times[b]:
                times[b] = t
    marker_bills = set(times)
    for ref in brefs.scan_bill_refs(d):
        b, t = ref['bill'], ref['time']
        if known_bills is not None and b not in known_bills and b not in marker_bills:
            continue
        if b not in times or t < times[b]:
            times[b] = t
    out = []
    for b, t in times.items():
        sec = dm.section_for(sections, t) if sections else None
        anchor = int(sec['start']) if sec else 0
        out.append({'bill': b, 'anchor': anchor})
    out.sort(key=lambda x: x['anchor'])
    return out


def render_program(d):
    p = d['program']
    e = html.escape
    is_floor = p['series_id'] in FLOOR_SERIES
    ptype = 'Floor session' if is_floor else 'Committee hearing'
    speakers = sorted({n for s in d['sections'] for n in s['persons']})
    bill_segments = [{'bill': b, 'start': s['start'], 'end': s['end']}
                     for s in d['sections'] for b in s['bills']]
    video = VIDEO_URL_TEMPLATE.format(pid=p['id'])

    bic = bills_in_context(d)

    def _bill_line(item):
        num = item['bill']
        compact = num.replace(' ', '')
        tracker = f'../ohio-legislation-tracker-LIVE.html?bill={e(compact)}&ga=136'
        return (f'<li><a href="#t{item["anchor"]}">{e(num)}</a> '
                f'<a class="track" href="{tracker}" target="_blank" rel="noopener">tracker &#8599;</a></li>')

    bills_panel = ('<section class="bills"><h2>Bills discussed</h2><ul>'
                   + ''.join(_bill_line(b) for b in bic)
                   + '</ul></section>') if bic else ''

    parts = [f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(p['name'])} — transcript</title><style>{PAGE_CSS}</style></head>
<body data-pagefind-body>
<div style="display:none">
<span data-pagefind-filter="chamber">{e(p['chamber'] or '')}</span>
<span data-pagefind-filter="type">{ptype}</span>
{''.join(f'<span data-pagefind-filter="speaker">{e(n)}</span>' for n in speakers)}
<span data-pagefind-meta="date">{e(p['release_date'])}</span>
<span data-pagefind-meta="program_id">{p['id']}</span>
<span data-pagefind-meta="series_name">{e(p['series_name'])}</span>
<span data-pagefind-meta="ptype">{ptype}</span>
<span data-pagefind-meta="bill_segments[data-json]" data-json="{e(json.dumps(bill_segments))}"></span>
</div>
<p class="meta"><a href="../transcripts.html">&larr; Search all transcripts</a></p>
<h1>{e(p['name'])}</h1>
<p class="meta">{e(p['release_date'])} · {e(p['series_name'])} · {ptype}
 · <a href="{video}">Watch on ohiochannel.org</a></p>
{f'<p class="meta">{SPEAKER_NOTE}</p>' if not is_floor else ''}
{bills_panel}"""]

    for s in d['sections']:
        parts.append(f'<h2 id="t{int(s["start"])}">{hms(s["start"])} · {e(s["label"])}</h2>')
        for chunk in _chunks(d['captions'], s['start'], s['end']):
            ts = int(chunk['start'])
            seek = video + VIDEO_TIME_PARAM.format(seconds=ts)
            parts.append(f'<h3 id="t{ts}"><a href="{seek}" title="Watch from {hms(ts)}">'
                         f'{hms(ts)}</a></h3>')
            parts.append(f"<p>{e(' '.join(chunk['lines']))}</p>")

    parts.append(f'<div class="footer" data-pagefind-ignore>{FOOTER_TEXT}</div></body></html>')
    return '\n'.join(parts)


def render_index(programs_index):
    e = html.escape
    rows = []
    for item in programs_index:
        if item.get('captions'):
            rows.append(f'<li><a href="{item["id"]}.html">{e(item["name"])}</a> '
                        f'<span class="meta">{e(item.get("date") or "")}</span></li>')
        else:
            rows.append(f'<li style="color:#999">{e(item["name"])} '
                        f'<span class="meta">{e(item.get("date") or "")} — captions not yet available</span></li>')
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Statehouse meeting transcripts</title><style>{PAGE_CSS}</style></head>
<body data-pagefind-ignore>
<p class="meta"><a href="../transcripts.html">&larr; Search all transcripts</a></p>
<h1>All meetings</h1><ul>{''.join(rows)}</ul>
<div class="footer">{FOOTER_TEXT}</div></body></html>"""


def render_all(programs_dir, index_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    count = 0
    for path in sorted(glob.glob(os.path.join(programs_dir, '*.json.gz'))):
        d = dm.load_distilled(path)
        out = os.path.join(out_dir, f"{d['program']['id']}.html")
        with open(out, 'w', encoding='utf-8') as f:
            f.write(render_program(d))
        count += 1
    with open(index_path, encoding='utf-8') as f:
        programs_index = json.load(f)
    with open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(render_index(programs_index))
    return count
