# ohio-legislation-tracker
Ohio legislative tracking widgets for Signal Ohio

## Statehouse Transcripts

`transcripts.html` — searchable transcripts of Ohio House and Senate floor
sessions and committee hearings for the current General Assembly.

**Data source:** The Ohio Channel's closed captions and agenda markers, via
their public JSON API. A nightly GitHub Action fetches captions for new
meetings only (about two requests per meeting, throttled to one request per
second, with an identifying User-Agent: `ohio-legislation-tracker
(scott@signalohio.org)`). Readers never hit the Ohio Channel's servers —
all search runs against this repo's archived copy via a static
[Pagefind](https://pagefind.app) index built at deploy time.

**Caveats:** Transcripts come from closed captions and are not an official
record — verify against the linked video before quoting. Speaker names are
available for floor sessions only (from the Ohio Channel's agenda markers);
committee hearings have no speaker tagging. Meetings whose captions haven't
been posted yet are listed as "captions not yet available."

**Pipeline:** `fetch_transcripts.py` (nightly fetch) →
`build_transcript_derived.py` (index/topics) → `build_site.py` +
Pagefind (deploy). Curated topics live in
`ohio_transcript_data/topics_curated.json`. At the January 2027 GA rollover,
update `build_series_config.py` and regenerate the series config.
