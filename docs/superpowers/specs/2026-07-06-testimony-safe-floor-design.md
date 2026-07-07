# Testimony Safe Floor + possible_vote — Design

**Date:** July 6, 2026
**Status:** Approved in conversation (accuracy audit → risk/benefit → "let's do it")
**Scope:** `ohio-committee-hearings-LIVE.html` + the agenda-item mapping in `.github/workflows/fetch-hearings.yml`. The notice-PDF parser is explicitly deferred pending floor-frequency data once session resumes.

## Problem (from the July 6 accuracy audit)

1. When a committee notice says "All Testimony," the LIS API's four per-type
   booleans stay false — the widget asserts "No public testimony this hearing"
   on a fully open hearing (confirmed: SB315, House Finance, June 9). False-
   closed is the worst error a testimony tool can make.
2. The API carries `possible_vote` / `possible_sub_bill` / `type`
   (`pending_intro`) which we don't read. The vote-stage badge is inferred
   from hearing count (4th+), which ground truth shows is wrong in both
   directions.

## Design

**Fetcher (workflow inline Python):** agenda-item dict gains
`possible_vote`, `possible_sub_bill` (booleans) and `item_type` (the API's
`type`, default `'hearing'`). The widget's live-API path
(`enrichWithAgendaItems`) maps the same three fields.

**Widget logic:**

- Badge class: `possible_vote` → `vote-stage`; else hearing number ≥ 3 →
  `late-stage`. Status text gains " • Vote possible" when `possible_vote`.
  (Old cached data lacking the field degrades to the count heuristic's
  late-stage styling for at most one 6-hour cycle.)
- Testimony badges, per item:
  - `sponsor` → "Sponsor presentation" (unchanged)
  - any of proponent/opponent/interested_party → open badges (unchanged)
  - all false AND (`possible_vote` OR `possible_sub_bill` OR
    `item_type === 'pending_intro'`) → "No public testimony this hearing"
    (audit verified these are genuinely closed)
  - all false and none of the above → **"Testimony status not listed —
    check the official notice"** (new `unknown` styling, amber). Never
    assert closed without evidence.
- `getTestimonySummary` gains the same distinction: if nothing is open but
  any item is unknown, the hearing-level summary says "Testimony status not
  listed for this hearing — check the official notice" instead of "No
  public testimony."
- Bill link guard: only build the legislature.ohio.gov bill href when
  `item.id` matches `/^[a-z]{2,3}\d+$/` (pending_intro items carry raw
  "S. B. No. 450"-style ids that made broken URLs).

**CSS:** `.testify-badge.unknown` and `.testimony-summary.unknown` — amber
(#fef3c7 / #92400e), distinct from green open and gray closed.

## Verification

No JS harness; verify by injecting synthetic agenda items in the browser
(localhost http.server) covering: open flags, sponsor-only, all-false+vote,
all-false+sub-bill, all-false+pending_intro, all-false+nothing (→ unknown),
mixed hearing (open + unknown summary), old-format item missing the new
fields. Then push and re-verify live once the next 6-hour fetch delivers
enriched data (until then live agenda_items are empty — JCARR only).
