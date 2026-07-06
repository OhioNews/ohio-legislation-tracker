# Signed-into-law terminal state — design

**Date:** 2026-07-06
**Status:** Approved by Scott (label choice: "Became Law" hybrid)

## Problem

LegiScan status 3 (Enrolled — passed both chambers, on the governor's desk) and
status 4 (Passed — became law) both map to the single status string `passed` in
`fetch_ohio_legislation.py`. The bill progress bar's fifth step can therefore
never light. The same conflation blocks the joint-resolution track's "On
Ballot" step. As of July 6, 2026: 103 HB/SB bills sit at `passed`, at least 85
of which are already law.

Label accuracy constraint: Ohio bills can become law **without** a signature
(10-day rule) or **over a veto** (override). "Signed into Law" would be wrong
in both cases, so the universal label is **"Became Law"**. Mechanism-specific
labels are deferred until we inventory LegiScan's actual Ohio history strings
(see Migration).

## Fetcher changes (`fetch_ohio_legislation.py`)

- Status mapping becomes type-aware, keyed off the bill number prefix
  (HB/SB = bill; HJR/SJR = joint resolution; HR/SR/HCR/SCR = resolution):
  - **HB/SB:** 1→`introduced`, 2→`passed-chamber`, 3→`passed`,
    4→`became-law` (new), 5→`vetoed`, 6→`failed`
  - **HJR/SJR:** 4→`on-ballot` (new); 3 stays `passed`
  - **HR/SR/HCR/SCR:** 3 and 4 both stay `passed` (Adopted) — unchanged
- Every bill record gains `status_code` (the raw LegiScan integer) so future
  mapping changes are a local re-derive, not a full API refetch.
- Changes-feed noise filter (`build_change_entries`): skip an entry when
  `last_action` **and** `last_action_date` are unchanged, even if the derived
  status string changed. Real status changes always arrive with a new history
  action; this keeps the one-time migration out of the What Moved feed.
- **Governor-string inventory (one-time, stays in the code):** during each
  run, collect distinct history action strings matching
  `governor|sign|veto|override` (case-insensitive) across fetched bills and
  print the sorted set at the end of the run log. The migration refetch pulls
  all 2,408 full histories, so its Actions log becomes the inventory for
  deciding whether mechanism-specific labels ("Signed into Law," "Became Law —
  veto overridden") are feasible as a follow-up.

## Widget changes (`ohio-legislation-tracker-LIVE.html`)

- Bill track fifth step: key `became-law`, label **"Became Law"**, icon 📜
  (replaces the dead `governor` key / 🖊️ pen icon, which implied signing).
- Joint-resolution track fifth step: key `on-ballot` (label "On Ballot" 🗳️
  unchanged). Simple/concurrent resolution tracks unchanged.
- Status filter: add "Became Law" (`became-law`) and "On Ballot" (`on-ballot`)
  options; `syncStatusLabels` relabels them type-aware, following the existing
  "Vetoed (bills only)" pattern.
- Sort-by-status order: `['introduced','in-committee','passed-chamber',
  'passed','on-ballot','became-law','vetoed','failed']`.
- Vetoed/failed terminal banners unchanged; a bill at status 3 shows "Passed
  Both" lit with "Became Law" pending — which reads correctly as "on the
  governor's desk."

## Migration & deploy

- Same commit: delete `ohio_legislation_data/bill_hashes.json` (forces a full
  refetch and re-derive of all 2,408 records; ~2,400 LegiScan calls, ~8% of
  the 30k monthly quota) and bump the workflow `timeout-minutes` from 30 to 45
  (no rate-limit sleep in the fetch loop; a slow API day could brush 30).
- Push `clean:main`, trigger `update-legislation.yml`, then verify: signed
  bills show a completed bar, adopted HJR/SJRs light "On Ballot," adopted
  resolutions still read "Adopted," `changes.json` is created and
  noise-filtered, and the governor-string inventory appears in the run log.
- Known transient: between Pages deploying the new HTML and the migration run
  committing re-derived data, `became-law` bills display as today ("Passed
  Both"). Harmless, self-resolves.

## Testing

- Unit tests (`test_fetch_ohio_legislation.py`, run with
  `PYTHONIOENCODING=utf-8`): type-aware mapping for all four prefixes
  (including resolutions unchanged at 3/4), `status_code` passthrough, noise
  filter skips status-only changes but keeps real action changes.
- Frontend: local `http.server` with fixture data covering a became-law bill,
  an enrolled (status 3) bill, an on-ballot JR, an adopted resolution and a
  vetoed bill; verify bars, filter options and sort order in the browser.

## Deferred follow-up

- Mechanism-specific labels (signed / no signature / veto override), pending
  the string inventory from the migration run.
- No new UI for the enrolled state beyond the pending fifth step.
