# Deep Links — Design

**Date:** July 6, 2026
**Status:** Approved pending Scott's spec review
**Scope:** `ohio-legislation-tracker-LIVE.html` only. Frontend-only; no fetcher, data-file or Actions changes.

## Purpose

Make individual bills shareable and addressable. A URL like
`https://ohionews.github.io/ohio-legislation-tracker/ohio-legislation-tracker-LIVE.html?bill=HB96&ga=136`
opens the tracker scrolled to HB96 with its description expanded. A copy-link
button on each bill card mints these URLs. This is the enabler for the
watched-bills curation file (next roadmap item) and for sharing bills with
reporters.

## Decisions made in brainstorming

- **Both directions:** inbound URL handling and an outbound copy-link button per card.
- **Query param** (`?bill=`), not hash fragment. Matches roadmap notation; plain
  anchors can't work because the target is usually beyond pagination or hidden
  by filters.
- **Auto-expand** the linked bill's "Read more" description on arrival.
- **No address-bar syncing** while browsing. The copy button is the only way a
  shareable URL is minted; reloading during daily monitoring never re-jumps.
- **Session stamp:** minted links include `&ga=136` so every link in the wild is
  self-identifying when the 137th GA arrives in January 2027. Read-side
  mismatch handling is deferred to the session-rollover work (Phase 3).
- **Quiet failure:** an unknown bill number logs to console and the page loads
  normally — no dialog, no toast.

## Design

### 1. Inbound: `handleDeepLink()`

Called once at the end of `loadBills()`'s success path, after
`displayNewThisWeek()` (the list is rendered and `allBills` is populated by then).

1. Read `bill` and `ga` from `new URLSearchParams(location.search)`. No `bill`
   param → return immediately (the everyday case).
2. Normalize: uppercase and strip all whitespace, so `?bill=hb 96` matches the
   data's `HB96` format. Match against `allBills` with the same normalization
   applied to `b.number`.
3. Not found → `console.warn` and return; page behaves as a normal load.
4. If `ga` is present and ≠ `CURRENT_GA`, `console.warn` the mismatch (still
   jump — until rollover, the data is the 136th either way). The user-facing
   mismatch notice is explicitly deferred to the session-rollover plan.
5. Call the existing `jumpToBill()` with the matched bill's own `number` string
   (not the raw URL param) — it already widens filters, extends pagination,
   scrolls and flash-highlights.
6. Expand the description: find `#desc-<id>` and its `.description-toggle`
   button inside the bill card; if the description exists and is collapsed,
   invoke the same expand path `toggleDescription()` uses (description may be
   absent — ~730 bills have none beyond the title — so null-check).

### 2. Outbound: copy-link button

- A small link button (🔗) added to `.bill-header` in `createBillHTML()`,
  rendered after the badges. Styled to match existing badge/button scale;
  `aria-label="Copy link to <bill number>"`.
- Click → build `location.origin + location.pathname + '?bill=' + number +
  '&ga=' + CURRENT_GA` (bill numbers are alphanumeric, no encoding needed;
  strip whitespace to match the normalized inbound format) →
  `navigator.clipboard.writeText()`.
- Success: button content swaps to "✓ Copied" for 1.5 s (mirrors the
  flash-highlight timing), then reverts.
- Failure (clipboard API rejected): button shows "Copy failed" for 1.5 s and
  the error logs to console. GitHub Pages is HTTPS and localhost is a secure
  context, so the API is available everywhere this widget runs.

### 3. `CURRENT_GA` constant

`const CURRENT_GA = 136;` added alongside the existing config constants. The
footer's hardcoded "136th General Assembly" line is left as-is; centralizing
all session references is part of the session-rollover work, which this
constant gives a head start.

## Out of scope (deliberate)

- Filter/search-state deep links — bills only.
- Address-bar `replaceState` syncing on chip clicks or jumps.
- User-facing not-found or session-mismatch messaging.
- Read-side `ga` handling beyond a console warning (deferred to rollover plan).
- Any change to the hearings widget or news aggregator.

## Error handling summary

| Case | Behavior |
|---|---|
| No `?bill=` param | Normal load, zero extra work |
| Unknown bill number | `console.warn`, normal load |
| `ga` mismatch | `console.warn`, jump anyway (until rollover work lands) |
| Bill has no description | Jump + flash only, no expand attempt |
| Clipboard write fails | "Copy failed" on button for 1.5 s, console error |

## Testing

Manual browser verification via `python -m http.server` (the project's
established pattern), covering:

1. `?bill=HB96` — jumps, flashes, description expands.
2. `?bill=hb 96` — normalization works.
3. A resolution hidden by the default type filter — filters widen, jump lands.
4. A bill deep in pagination — pagination extends, jump lands.
5. `?bill=HB9999` — console warning, page otherwise normal.
6. No param — behavior identical to today.
7. Copy button — clipboard contains the full URL with `&ga=136`; "✓ Copied"
   feedback appears and reverts; pasting the URL into a new tab round-trips
   to the same bill.

## Maintenance

Zero recurring upkeep. One scheduled touchpoint: the January 2027 session
rollover adds read-side `ga` mismatch messaging (already on the Phase 3 list;
this design's `ga` stamp on minted links is what makes that detection possible).
