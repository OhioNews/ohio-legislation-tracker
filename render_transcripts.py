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
.findbar{font-family:system-ui,sans-serif;font-size:.85rem;display:flex;align-items:center;gap:.4rem;
margin:.8rem 0;padding:.5rem .6rem;background:#f7f5f0;border:1px solid #e2ded2;border-radius:.4rem;
position:sticky;top:0;z-index:5}
.findbar input{flex:1;font:inherit;padding:.3rem .5rem;border:1px solid #ccc;border-radius:.3rem;min-width:0}
.findbar button{font:inherit;border:1px solid #ccc;background:#fff;border-radius:.3rem;padding:.2rem .55rem;cursor:pointer}
.findbar button:hover{background:#eee}
.findcount{color:#666;min-width:4.2rem;text-align:center;white-space:nowrap}
mark.find-hit{background:#ffe58a;color:inherit;padding:0 1px;border-radius:2px}
mark.find-hit.current{background:#ff8c00;color:#fff}
"""

# Highlight-and-skip-through find widget for a single transcript page. Runs
# entirely client-side over the already-rendered <p> text (no data/build
# changes). Scoped to `p:not(.meta)` so it only touches caption text, never
# the date/series/speaker meta lines. ?find= in the URL pre-loads a term
# (wired up from the free-text search results page, where the term is a
# confirmed literal match).
FIND_WIDGET_SCRIPT = """<script>
(function(){
  var paras=Array.prototype.slice.call(document.querySelectorAll('p:not(.meta)'));
  var originals=paras.map(function(p){return p.textContent});
  var hits=[],current=-1;
  var input=document.getElementById('findInput'),countEl=document.getElementById('findCount');
  function escapeRe(s){return s.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')}
  function clearHighlights(){paras.forEach(function(p,i){p.textContent=originals[i]});hits=[];current=-1}
  function updateCount(){countEl.textContent=hits.length?(current+1)+' of '+hits.length:(input.value?'0 of 0':'')}
  function markCurrent(){
    hits.forEach(function(h,i){h.classList.toggle('current',i===current)});
    if(current>=0)hits[current].scrollIntoView({block:'center',behavior:'smooth'});
  }
  function runFind(term){
    clearHighlights();
    if(!term){updateCount();return}
    var re=new RegExp('('+escapeRe(term)+')','gi');
    paras.forEach(function(p,i){
      var text=originals[i];
      re.lastIndex=0;
      if(!re.test(text))return;
      re.lastIndex=0;
      var frag=document.createDocumentFragment(),last=0,m;
      while((m=re.exec(text))){
        if(m[0].length===0){re.lastIndex++;continue}
        frag.appendChild(document.createTextNode(text.slice(last,m.index)));
        var mark=document.createElement('mark');
        mark.className='find-hit';mark.textContent=m[0];
        frag.appendChild(mark);hits.push(mark);
        last=m.index+m[0].length;
      }
      frag.appendChild(document.createTextNode(text.slice(last)));
      p.textContent='';p.appendChild(frag);
    });
    current=hits.length?0:-1;
    markCurrent();updateCount();
  }
  function next(){if(!hits.length)return;current=(current+1)%hits.length;markCurrent();updateCount()}
  function prev(){if(!hits.length)return;current=(current-1+hits.length)%hits.length;markCurrent();updateCount()}
  input.addEventListener('input',function(){runFind(input.value.trim())});
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'){e.preventDefault();e.shiftKey?prev():next()}
    else if(e.key==='Escape'){input.value='';runFind('');input.blur()}
  });
  document.getElementById('findNext').onclick=next;
  document.getElementById('findPrev').onclick=prev;
  document.getElementById('findClear').onclick=function(){input.value='';runFind('');input.focus()};
  var q=new URLSearchParams(location.search).get('find');
  if(q){input.value=q;runFind(q)}
})();
</script>"""


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


def render_program(d):
    p = d['program']
    e = html.escape
    is_floor = p['series_id'] in FLOOR_SERIES
    ptype = 'Floor session' if is_floor else 'Committee hearing'
    speakers = sorted({n for s in d['sections'] for n in s['persons']})
    bill_segments = [{'bill': b, 'start': s['start'], 'end': s['end']}
                     for s in d['sections'] for b in s['bills']]
    video = VIDEO_URL_TEMPLATE.format(pid=p['id'])

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
<div class="findbar" data-pagefind-ignore>
<input id="findInput" type="text" placeholder="Find in this transcript…" aria-label="Find in transcript" autocomplete="off">
<button id="findPrev" type="button" title="Previous match (Shift+Enter)">&uarr;</button>
<button id="findNext" type="button" title="Next match (Enter)">&darr;</button>
<span id="findCount" class="findcount"></span>
<button id="findClear" type="button" title="Clear">&times;</button>
</div>"""]

    for s in d['sections']:
        parts.append(f'<h2 id="t{int(s["start"])}">{hms(s["start"])} · {e(s["label"])}</h2>')
        for chunk in _chunks(d['captions'], s['start'], s['end']):
            ts = int(chunk['start'])
            seek = video + VIDEO_TIME_PARAM.format(seconds=ts)
            parts.append(f'<h3 id="t{ts}"><a href="{seek}" title="Watch from {hms(ts)}">'
                         f'{hms(ts)}</a></h3>')
            parts.append(f"<p>{e(' '.join(chunk['lines']))}</p>")

    parts.append(f'<div class="footer" data-pagefind-ignore>{FOOTER_TEXT}</div>')
    parts.append(FIND_WIDGET_SCRIPT)
    parts.append('</body></html>')
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
