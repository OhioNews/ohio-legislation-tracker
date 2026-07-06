# Deep Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Individual bills get shareable URLs (`?bill=HB96&ga=136`) plus a per-card copy-link button, per the approved spec at `docs/superpowers/specs/2026-07-06-deep-links-design.md`.

**Architecture:** Frontend-only changes to the self-contained widget `ohio-legislation-tracker-LIVE.html`. Inbound: parse `?bill=` after data load and hand off to the existing `jumpToBill()`. Outbound: a copy button in each bill card's badge row mints the URL via `navigator.clipboard`.

**Tech Stack:** Vanilla JS inside one HTML file. No build step, no test harness for the frontend — this project's established verification pattern is manual browser testing against `python -m http.server` (same as Phases 0–2). Steps below substitute exact manual verification for automated tests; the Python unittest suite is untouched because no fetcher code changes.

## Global Constraints

- Only `ohio-legislation-tracker-LIVE.html` may change. No fetcher, data-file, workflow or hearings/news-widget changes.
- All failure modes are quiet: `console.warn`/`console.error` only, no dialogs or toasts (spec "Quiet failure").
- Minted URLs use the compact bill-number format (`HB96`, no space) and include `&ga=136`.
- No address-bar writes ever (`history.pushState`/`replaceState` must not appear).
- Local branch is `clean`; push to live is `git push origin clean:main` and happens only in Task 3.
- Work repo = GitHub account **ohionews** (the gh CLI defaults to WrittenWords — irrelevant here since only `git push` is used, but do not use `gh` for pushes).

---

### Task 1: `CURRENT_GA` constant + copy-link button (outbound)

**Files:**
- Modify: `ohio-legislation-tracker-LIVE.html`
  - config constants block (~line 1007)
  - CSS badge section (after `.bill-badges` rule, ~line 523)
  - `createBillHTML()` badge row (~line 1669)
  - new functions `copyBillLink()` / `showCopyFeedback()` (place directly after `toggleDescription()`, ~line 1907)

**Interfaces:**
- Consumes: `bill.number` strings as stored in bills.json (compact, e.g. `HB96`); existing `.badge` styling vars.
- Produces: `const CURRENT_GA = 136` (Task 2 reads it); global `copyBillLink(billNumber, button)` invoked from card markup.

- [ ] **Step 1: Add the constant**

In the config block (directly under `const CHANGES_FILE_PATH = ...`, ~line 1009):

```js
const CURRENT_GA = 136; // General Assembly number stamped into shared links
```

- [ ] **Step 2: Add the button CSS**

Insert after the `.bill-badges` rule (~line 523), before `.badge`:

```css
.copy-link-btn {
    padding: 6px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
    background: none;
    border: 1px solid var(--border, #ddd);
    color: var(--text-light);
    cursor: pointer;
    transition: border-color 0.2s, color 0.2s;
}

.copy-link-btn:hover {
    border-color: var(--signal-dark);
    color: var(--signal-dark);
}
```

(If the stylesheet has no `--border` variable, keep the `#ddd` fallback as written — check the `:root` block rather than adding a new variable.)

- [ ] **Step 3: Render the button in each card**

In `createBillHTML()` (~line 1669), add the button as the last item inside `.bill-badges`:

```html
<div class="bill-badges">
    ${isPriority ? '<span class="badge badge-priority">⭐ PRIORITY</span>' : ''}
    ${isNew ? '<span class="badge badge-new">🆕 NEW</span>' : ''}
    <span class="badge badge-chamber">${chamberText}</span>
    ${typeBadge}
    <button class="copy-link-btn" onclick="copyBillLink('${bill.number}', this)" aria-label="Copy link to ${bill.number}">🔗 Copy link</button>
</div>
```

(Bill numbers are alphanumeric — `HB96` — so single-quote interpolation is safe; this mirrors the existing `jumpToBill('${mover.number}')` pattern.)

- [ ] **Step 4: Implement the copy functions**

Directly after `toggleDescription()` (~line 1907):

```js
// Copy a shareable deep link for a bill to the clipboard
function copyBillLink(billNumber, button) {
    const compact = billNumber.replace(/\s+/g, '');
    const url = `${location.origin}${location.pathname}?bill=${compact}&ga=${CURRENT_GA}`;
    navigator.clipboard.writeText(url).then(() => {
        showCopyFeedback(button, '✓ Copied');
    }).catch((err) => {
        console.error('Copy failed:', err);
        showCopyFeedback(button, 'Copy failed');
    });
}

// Swap button text for 1.5s (mirrors flash-highlight timing), then restore
function showCopyFeedback(button, message) {
    const original = button.textContent;
    button.textContent = message;
    button.disabled = true;
    setTimeout(() => {
        button.textContent = original;
        button.disabled = false;
    }, 1500);
}
```

- [ ] **Step 5: Verify in browser**

Run from the repo root: `python -m http.server 8000`
Open: `http://localhost:8000/ohio-legislation-tracker-LIVE.html`

Check:
1. Every bill card shows a "🔗 Copy link" button at the end of its badge row, on desktop width and at ≤768px (badges wrap; button wraps with them).
2. Click the button on HB96's card → button reads "✓ Copied" then reverts after ~1.5s.
3. Paste clipboard → exactly `http://localhost:8000/ohio-legislation-tracker-LIVE.html?bill=HB96&ga=136`.
4. Console shows no errors.
5. Cards in the "What Moved" section also carry the button (they render through the same `createBillHTML`).

- [ ] **Step 6: Commit**

```bash
git add ohio-legislation-tracker-LIVE.html
git commit -m "Add per-bill copy-link button minting ?bill=&ga= deep links

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Inbound deep-link handling + auto-expand

**Files:**
- Modify: `ohio-legislation-tracker-LIVE.html`
  - `loadBills()` success path (~line 1123, after `displayNewThisWeek()`)
  - new function `handleDeepLink()` (place directly after `jumpToBill()`, ~line 1474)

**Interfaces:**
- Consumes: `CURRENT_GA` from Task 1; existing `jumpToBill(billNumber)` (widens filters, extends pagination, scrolls, flashes); existing `toggleDescription(descId, button)`; `allBills` populated by `loadBills()`.
- Produces: `handleDeepLink()` — called once per page load; no other callers.

- [ ] **Step 1: Implement `handleDeepLink()`**

Directly after `jumpToBill()`'s closing brace (~line 1474):

```js
// Deep link: ?bill=HB96&ga=136 jumps to a bill on load and expands
// its description. Quiet failure — unknown bills log and fall through
// to a normal page load. ga mismatch handling is deferred to the
// session-rollover work; until then it only warns.
function handleDeepLink() {
    const params = new URLSearchParams(location.search);
    const rawBill = params.get('bill');
    if (!rawBill) return;

    const target = rawBill.replace(/\s+/g, '').toUpperCase();
    const bill = allBills.find(b => b.number.replace(/\s+/g, '').toUpperCase() === target);
    if (!bill) {
        console.warn(`Deep link: bill "${rawBill}" not found in current data`);
        return;
    }

    const ga = params.get('ga');
    if (ga && parseInt(ga, 10) !== CURRENT_GA) {
        console.warn(`Deep link: minted for GA ${ga}, current is GA ${CURRENT_GA}`);
    }

    jumpToBill(bill.number);

    // Auto-expand the description, if the bill has one (~730 don't)
    const idSuffix = bill.number.replace(/\s+/g, '-');
    const card = document.getElementById(`bill-${idSuffix}`);
    const desc = document.getElementById(`desc-${idSuffix}`);
    if (card && desc && desc.classList.contains('collapsed')) {
        const toggleBtn = card.querySelector('.description-toggle');
        if (toggleBtn) toggleDescription(`desc-${idSuffix}`, toggleBtn);
    }
}
```

- [ ] **Step 2: Call it from `loadBills()`**

At the end of the success path, immediately after `displayNewThisWeek();` (~line 1123):

```js
displayNewThisWeek();
handleDeepLink();
```

(`applyFilters()` has already rendered the list synchronously by this point, so the card is findable or `jumpToBill` can make it so.)

- [ ] **Step 3: Find a hidden-by-default resolution number for testing**

Run from the repo root:

```bash
grep -o '"number": "SCR[0-9]*"' ohio_legislation_data/bills.json | head -3
```

Note one number (e.g. `SCR7`) — simple/concurrent resolutions are excluded by the default type filter, which is exactly the widening path to exercise. If SCR yields nothing, try `HR` in the same command.

- [ ] **Step 4: Verify in browser**

With `python -m http.server 8000` still running, test each URL:

1. `...?bill=HB96&ga=136` — page scrolls to HB96, card flashes, "Read more" description is expanded (toggle reads "Show less ▲").
2. `...?bill=hb 96` — same result (`%20` or literal space both fine): normalization works, and a missing `ga` is fine.
3. `...?bill=<SCR number from Step 3>` — type filter visibly widens (dropdown changes), jump lands on the resolution.
4. `...?bill=HB9999` — console shows the not-found warning; page otherwise identical to a normal load.
5. `...?bill=HB96&ga=135` — jump still works; console shows the GA-mismatch warning.
6. No query string — behavior identical to today, nothing in console.
7. A bill without a description (search the rendered page for a card with no "Read more" button, then deep-link to it) — jump + flash, no console error.

- [ ] **Step 5: Commit**

```bash
git add ohio-legislation-tracker-LIVE.html
git commit -m "Handle ?bill= deep links: jump, flash and expand on load

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Round-trip verification and ship

**Files:**
- Modify: none (verification + push only)

**Interfaces:**
- Consumes: everything from Tasks 1–2.
- Produces: feature live on GitHub Pages.

- [ ] **Step 1: Round-trip test**

On `http://localhost:8000/ohio-legislation-tracker-LIVE.html`: click 🔗 on any bill mid-list, open the pasted URL in a new tab, confirm it lands on that same bill expanded and flashed. Repeat once from a "What Moved" card.

- [ ] **Step 2: Regression spot-check**

Confirm the feature didn't disturb existing behavior: search box, type filter, "What Moved" chip jump, Read more toggle, and pagination "Show more" all work as before. Console clean throughout.

- [ ] **Step 3: Push to live**

```bash
git push origin clean:main
```

- [ ] **Step 4: Verify live**

Open `https://ohionews.github.io/ohio-legislation-tracker/ohio-legislation-tracker-LIVE.html?bill=HB96&ga=136` after Pages deploys (a minute or two). Confirm jump + expand, and that the copy button mints the full https URL (clipboard API requires the secure context — GitHub Pages is HTTPS, so this is the real-world check).
