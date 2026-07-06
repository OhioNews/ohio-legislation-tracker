# Signed-Into-Law Terminal State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distinguish LegiScan status 3 (on the governor's desk) from status 4 (became law) so the bill tracker's terminal progress steps — "Became Law" for bills, "On Ballot" for joint resolutions — actually light up, then migrate all 2,408 existing records.

**Architecture:** The Python fetcher derives a type-aware status string per bill (keyed off the bill-number prefix) and stores the raw LegiScan status code for future remaps. The self-contained HTML widget renders the new terminal steps, filter options and sort order. A one-time full refetch (delete `bill_hashes.json`) migrates existing data; a changes-feed noise-filter change keeps that migration out of the "What Moved" feed.

**Tech Stack:** Python 3 (stdlib + requests), Python `unittest`, vanilla-JS single-file HTML widget, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-07-06-signed-into-law-design.md`

## Global Constraints

- Repo: `C:\Users\scott\OneDrive\Desktop\Work\ohio-legislation-tracker`, branch `clean`; deploy by pushing `git push origin clean:main`. Commits use the already-configured identity (scott@signalohio.org / OhioNews). gh CLI must be on the **OhioNews** account.
- Run tests with UTF-8 stdout on Windows PowerShell: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation -v` (the fetcher prints ✓/✗ glyphs that crash cp1252).
- New status strings are exactly `became-law` and `on-ballot` (kebab-case, matching `passed-chamber`). User-facing labels are exactly "Became Law" and "On Ballot" — never "Signed into Law" (bills can become law unsigned or over a veto).
- Resolutions (HR/SR/HCR/SCR) must keep status `passed` for LegiScan codes 3 **and** 4 — no behavior change for them.
- Don't run the real fetcher locally; the API key lives only in GitHub Actions. All local testing is via unittest mocks or fixture JSON.

---

### Task 1: Type-aware status mapping + raw status code (fetcher)

**Files:**
- Modify: `fetch_ohio_legislation.py` (imports at line 12-16; status block at lines 377-391; return dict at lines 402-416)
- Test: `test_fetch_ohio_legislation.py`

**Interfaces:**
- Produces: `get_bill_type(number) -> str` returning `'bill' | 'joint-resolution' | 'resolution'`; `format_bill_for_widget(bill)` output gains key `status_code` (raw LegiScan int) and may now return `status` values `became-law` / `on-ballot`. Tasks 2, 6 and 7 rely on these exact strings.

- [ ] **Step 1: Write the failing tests** — append to `test_fetch_ohio_legislation.py` (before the final `if __name__` block):

```python
class TestStatusMapping(unittest.TestCase):
    """Type-aware derivation of widget status from LegiScan status codes."""

    def formatted(self, number, status):
        b = minimal_bill(1, number)
        b['status'] = status
        return fetcher.format_bill_for_widget(b)

    def test_enrolled_bill_stays_passed_awaiting_governor(self):
        self.assertEqual(self.formatted('HB1', 3)['status'], 'passed')

    def test_status4_house_bill_became_law(self):
        self.assertEqual(self.formatted('HB1', 4)['status'], 'became-law')

    def test_status4_senate_bill_became_law(self):
        self.assertEqual(self.formatted('SB1', 4)['status'], 'became-law')

    def test_status4_joint_resolution_is_on_ballot(self):
        self.assertEqual(self.formatted('HJR2', 4)['status'], 'on-ballot')

    def test_status4_concurrent_resolution_stays_passed(self):
        self.assertEqual(self.formatted('SCR3', 4)['status'], 'passed')

    def test_status4_simple_resolution_stays_passed(self):
        self.assertEqual(self.formatted('HR4', 4)['status'], 'passed')

    def test_vetoed_unchanged(self):
        self.assertEqual(self.formatted('HB1', 5)['status'], 'vetoed')

    def test_raw_status_code_is_preserved(self):
        self.assertEqual(self.formatted('HB1', 4)['status_code'], 4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation.TestStatusMapping -v`
Expected: `test_status4_house_bill_became_law` and the JR/status_code tests FAIL (`'passed' != 'became-law'`, `KeyError: 'status_code'`); enrolled/resolution/vetoed tests already pass.

- [ ] **Step 3: Implement.** In `fetch_ohio_legislation.py`:

(a) Add `import re` after `import requests` (line 12 block).

(b) Add a helper directly above `format_bill_for_widget` (line 327):

```python
def get_bill_type(number):
    """
    Classifies a bill number by its letter prefix, mirroring the widget's
    getBillType(): HJR/SJR go to Ohio voters, HCR/SCR/HR/SR never reach
    the governor, everything else (HB/SB) is a bill.
    """
    match = re.match(r'^([A-Za-z]+)', number or '')
    prefix = match.group(1).upper() if match else ''
    if prefix in ('HJR', 'SJR'):
        return 'joint-resolution'
    if prefix in ('HCR', 'SCR', 'HR', 'SR'):
        return 'resolution'
    return 'bill'
```

(c) Replace the status block (current lines 377-388 — the comment, `status_map` and the `status =` line ONLY; the in-committee inference at lines 389-391 stays exactly as is, below the new block) with:

```python
    # Determine status using LegiScan's actual status codes:
    # 1=Introduced, 2=Engrossed (passed 1st chamber), 3=Enrolled (passed both),
    # 4=Passed (became law for bills; adopted for resolutions; filed with the
    # Secretary of State for joint resolutions), 5=Vetoed, 6=Failed/Dead
    status_code = bill.get('status')
    bill_type = get_bill_type(bill['bill_number'])
    status_map = {
        1: 'introduced',
        2: 'passed-chamber',  # Engrossed = passed first chamber
        3: 'passed',          # Enrolled = passed both chambers
        4: 'passed',
        5: 'vetoed',
        6: 'failed'
    }
    if bill_type == 'bill':
        # "Became law" not "signed": covers signature, the 10-day
        # no-signature rule and veto overrides
        status_map[4] = 'became-law'
    elif bill_type == 'joint-resolution':
        status_map[4] = 'on-ballot'
    status = status_map.get(status_code, 'introduced')
```

(d) In the return dict, add `'status_code': status_code,` on the line after `'status': status,`.

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation -v`
Expected: all tests PASS (existing suite plus 8 new).

- [ ] **Step 5: Commit**

```powershell
git add fetch_ohio_legislation.py test_fetch_ohio_legislation.py
git commit -m "Type-aware status mapping: became-law and on-ballot terminal states"
```

---

### Task 2: Changes-feed noise filter ignores mapping-only status changes

**Files:**
- Modify: `fetch_ohio_legislation.py:121-149` (`build_change_entries`)
- Test: `test_fetch_ohio_legislation.py` (class `TestChangesFeed`)

**Interfaces:**
- Consumes: Task 1's mapping (`status` 4 on HB → `became-law`).
- Produces: `build_change_entries` skips any bill whose `last_action` and `last_action_date` are both unchanged, regardless of status string. Task 7's migration run depends on this to keep ~85 remapped bills out of the feed.

- [ ] **Step 1: Write the failing test** — add to class `TestChangesFeed`:

```python
    def test_mapping_only_status_change_is_noise(self):
        # Derived status changed (migration remap: passed -> became-law)
        # but the bill took no new action -> keep it out of the feed
        self.write_bills([self.existing_hb1(status='passed',
                                            action='Effective', date='2026-03-01')])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 4  # now maps to became-law
        updated['status_date'] = '2026-03-01'
        updated['history'] = [{'action': 'Effective', 'date': '2026-03-01'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        self.assertEqual(self.read_changes(), [])

    def test_real_enactment_with_new_action_is_recorded(self):
        self.write_bills([self.existing_hb1(status='passed',
                                            action='Sent to Governor', date='2026-06-20')])
        updated = minimal_bill(1, 'HB1')
        updated['status'] = 4
        updated['history'] = [{'action': 'Signed by Governor', 'date': '2026-07-05'}]
        self.run_main_with(
            {'0': {'bill_id': 1, 'change_hash': 'new'}},
            {'1': updated},
            stored={'1': 'old'},
        )
        changes = self.read_changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['status'], 'became-law')
        self.assertEqual(changes[0]['prev_status'], 'passed')
```

- [ ] **Step 2: Run to verify the first fails**

Run: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation.TestChangesFeed -v`
Expected: `test_mapping_only_status_change_is_noise` FAILS (entry recorded because status differs); `test_real_enactment_with_new_action_is_recorded` PASSES already.

- [ ] **Step 3: Implement.** In `build_change_entries`, replace the skip condition (lines 133-137):

```python
        # A refetch that brought no new action is noise — even if the
        # derived status string changed (that only happens when our own
        # mapping changed; real status changes always add a history action)
        if old and \
           old.get('last_action') == b.get('last_action') and \
           old.get('last_action_date') == b.get('last_action_date'):
            continue
```

Also update the function docstring's noise sentence to match: "A bill whose hash changed but whose last action is identical (e.g. a new text version was uploaded, or only our status mapping changed) is treated as noise and skipped."

- [ ] **Step 4: Run the full suite**

Run: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation -v`
Expected: all PASS, including the pre-existing `test_status_change_recorded_with_previous_status` (its status change comes with a new action, so it must still be recorded).

- [ ] **Step 5: Commit**

```powershell
git add fetch_ohio_legislation.py test_fetch_ohio_legislation.py
git commit -m "Treat mapping-only status changes as noise in the changes feed"
```

---

### Task 3: Governor-action string inventory in the run log

**Files:**
- Modify: `fetch_ohio_legislation.py` (helper near `get_bill_type`; collection in `main()` fetch loop at lines 520-543; printout after the save section at line 599)
- Test: `test_fetch_ohio_legislation.py`

**Interfaces:**
- Consumes: raw LegiScan bill dicts (`bill['history']` list of `{'action', 'date'}`).
- Produces: `governor_actions_in(bill) -> set[str]`. Task 7 reads the printed inventory from the migration run's Actions log.

- [ ] **Step 1: Write the failing tests** — append to `test_fetch_ohio_legislation.py`:

```python
class TestGovernorActionInventory(unittest.TestCase):

    def test_collects_only_governor_related_actions(self):
        bill = minimal_bill(1, 'HB1')
        bill['history'] = [
            {'action': 'Introduced', 'date': '2026-01-01'},
            {'action': 'Assigned to Finance Committee', 'date': '2026-01-02'},
            {'action': 'Signed by Governor', 'date': '2026-06-01'},
            {'action': 'Vetoed by Governor', 'date': '2026-06-02'},
            {'action': 'House overrides veto', 'date': '2026-06-10'},
        ]
        self.assertEqual(
            fetcher.governor_actions_in(bill),
            {'Signed by Governor', 'Vetoed by Governor', 'House overrides veto'},
        )

    def test_bill_without_history_yields_empty_set(self):
        self.assertEqual(fetcher.governor_actions_in(minimal_bill(1, 'HB1')), set())
```

Note the "Assigned to Finance Committee" case: naive `sign` matching would collect it ("As**sign**ed") — the regex must anchor `sign` to a word start.

- [ ] **Step 2: Run to verify they fail**

Run: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation.TestGovernorActionInventory -v`
Expected: FAIL with `AttributeError: ... has no attribute 'governor_actions_in'`.

- [ ] **Step 3: Implement.** In `fetch_ohio_legislation.py`:

(a) Below `get_bill_type`, add:

```python
# \bsign (not bare "sign") so "Assigned to committee" doesn't match
GOVERNOR_ACTION_RE = re.compile(r'governor|\bsign|veto|override', re.IGNORECASE)


def governor_actions_in(bill):
    """
    Returns this bill's history actions that mention the governor or
    enactment mechanics (signing, vetoes, overrides). Logged each run to
    build a vocabulary of LegiScan's real Ohio action strings — the input
    for deciding whether mechanism-specific "Became Law" labels are viable.
    """
    return {
        event.get('action', '')
        for event in bill.get('history') or []
        if GOVERNOR_ACTION_RE.search(event.get('action', ''))
    }
```

(b) In `main()`, before the fetch loop (after `failed_count = 0`, line 518), add:

```python
    governor_actions = set()
```

(c) Inside the loop's success branch, after `all_hearings.extend(hearings)` (line 532), add:

```python
            governor_actions |= governor_actions_in(bill)
```

(d) After the changes-feed save print (line 599), add:

```python
    if governor_actions:
        print(f"\n7. Governor-related action strings seen this run ({len(governor_actions)}):")
        for action in sorted(governor_actions):
            print(f"   • {action}")
```

- [ ] **Step 4: Run the full suite**

Run: `$env:PYTHONIOENCODING='utf-8'; python -m unittest test_fetch_ohio_legislation -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add fetch_ohio_legislation.py test_fetch_ohio_legislation.py
git commit -m "Log distinct governor-action strings each run"
```

---

### Task 4: Widget — terminal progress steps and sort order

**Files:**
- Modify: `ohio-legislation-tracker-LIVE.html` (sort order line 1538; joint-resolution track lines 1567-1577; bill track lines 1602-1612)

**Interfaces:**
- Consumes: `status` values `became-law` / `on-ballot` from Task 1's data.
- Produces: rendered five-step tracks whose final step lights for those statuses. Verified in Task 6 (no JS test harness exists in this repo; the widget is a single self-contained file).

- [ ] **Step 1: Update the joint-resolution track.** Replace the `governor` step and `statusOrder` (lines 1575-1577):

```javascript
                    { key: 'on-ballot',     label: 'On Ballot',    icon: '🗳️' }
                ];
                statusOrder = ['introduced', 'in-committee', 'passed-chamber', 'passed', 'on-ballot'];
```

- [ ] **Step 2: Update the bill track.** Replace the `governor` step and `statusOrder` (lines 1610-1612):

```javascript
                    { key: 'became-law',    label: 'Became Law',  icon: '📜' }
                ];
                statusOrder = ['introduced', 'in-committee', 'passed-chamber', 'passed', 'became-law'];
```

(📜 replaces 🖊️ deliberately — a pen implies a signature that may never have happened.)

- [ ] **Step 3: Update the sort-by-status order** (line 1538):

```javascript
                    const order = ['introduced', 'in-committee', 'passed-chamber', 'passed', 'on-ballot', 'became-law', 'vetoed', 'failed'];
```

- [ ] **Step 4: Sanity-check by grep** — no `'governor'` key should remain:

Run: `Select-String -Path ohio-legislation-tracker-LIVE.html -Pattern "'governor'"`
Expected: no matches.

- [ ] **Step 5: Commit**

```powershell
git add ohio-legislation-tracker-LIVE.html
git commit -m "Widget: Became Law and On Ballot terminal progress steps"
```

---

### Task 5: Widget — status filter options and type-aware labels

**Files:**
- Modify: `ohio-legislation-tracker-LIVE.html` (dropdown lines 916-924; `syncStatusLabels` relabels lines 1160-1164)

**Interfaces:**
- Consumes: `status` values `became-law` / `on-ballot`; the existing exact-match filter (`bill.status === currentFilters.status`) needs no change.
- Produces: filter options with values `on-ballot` and `became-law`.

- [ ] **Step 1: Add the options.** In the status `<select>` (after line 921 `Passed Both`):

```html
                        <option value="on-ballot">On Ballot</option>
                        <option value="became-law">Became Law</option>
```

- [ ] **Step 2: Add type-aware relabels.** In `syncStatusLabels`, extend the `relabels` object (after the `'passed'` entry):

```javascript
                'on-ballot':      isBallot ? 'On Ballot' : 'On Ballot (ballot measures)',
                'became-law':     (isResolutions || isBallot) ? 'Became Law (bills only)' : 'Became Law',
```

- [ ] **Step 3: Verify the file parses** — open it briefly via the fixture server in Task 6, or run:

Run: `python -c "print(open('ohio-legislation-tracker-LIVE.html', encoding='utf-8').read().count('became-law'))"`
Expected: a number ≥ 4 (dropdown, relabel, track key, sort order).

- [ ] **Step 4: Commit**

```powershell
git add ohio-legislation-tracker-LIVE.html
git commit -m "Widget: filter options for Became Law and On Ballot"
```

---

### Task 6: Frontend verification in the browser (fixture data)

**Files:**
- Create (scratchpad, not the repo): `<scratchpad>\signed-law-fixture\ohio-legislation-tracker-LIVE.html` (copy of the repo file) and `<scratchpad>\signed-law-fixture\ohio_legislation_data\{bills.json, meta.json, changes.json}`

**Interfaces:**
- Consumes: Tasks 4-5's widget changes; the widget fetches `ohio_legislation_data/*.json` relative to its own URL, so a directory copy plus fixture data is a faithful harness.

- [ ] **Step 1: Build the fixture.** Copy the widget HTML into the scratchpad folder and write `bills.json` with six records covering every path (schema: same keys the fetcher emits — see Task 1 return dict):

```json
[
  {"bill_id": 1, "number": "HB10", "chamber": "house", "title": "Became-law bill", "description": "", "status": "became-law", "status_code": 4, "status_date": "2026-06-01", "last_action": "Effective", "last_action_date": "2026-06-01", "sponsor": "Rep. Test (R-1)", "committee": null, "subject": "general", "url": "https://legiscan.com/OH/bill/HB10/2025"},
  {"bill_id": 2, "number": "HB11", "chamber": "house", "title": "Enrolled bill on the governor's desk", "description": "", "status": "passed", "status_code": 3, "status_date": "2026-06-20", "last_action": "Sent to Governor", "last_action_date": "2026-06-20", "sponsor": "Rep. Test (R-2)", "committee": null, "subject": "general", "url": "https://legiscan.com/OH/bill/HB11/2025"},
  {"bill_id": 3, "number": "HJR1", "chamber": "house", "title": "CA: On-ballot measure", "description": "", "status": "on-ballot", "status_code": 4, "status_date": "2026-06-15", "last_action": "Filed with Secretary of State", "last_action_date": "2026-06-15", "sponsor": "Rep. Test (R-3)", "committee": null, "subject": "general", "url": "https://legiscan.com/OH/bill/HJR1/2025"},
  {"bill_id": 4, "number": "SCR2", "chamber": "senate", "title": "Adopted concurrent resolution", "description": "", "status": "passed", "status_code": 4, "status_date": "2026-05-01", "last_action": "Adopted", "last_action_date": "2026-05-01", "sponsor": "Sen. Test (D-4)", "committee": null, "subject": "general", "url": "https://legiscan.com/OH/bill/SCR2/2025"},
  {"bill_id": 5, "number": "HB12", "chamber": "house", "title": "Vetoed bill", "description": "", "status": "vetoed", "status_code": 5, "status_date": "2026-04-01", "last_action": "Vetoed by Governor", "last_action_date": "2026-04-01", "sponsor": "Rep. Test (D-5)", "committee": null, "subject": "general", "url": "https://legiscan.com/OH/bill/HB12/2025"},
  {"bill_id": 6, "number": "SB13", "chamber": "senate", "title": "In-committee bill", "description": "", "status": "in-committee", "status_code": 1, "status_date": "2026-06-25", "last_action": "Referred to committee", "last_action_date": "2026-06-25", "sponsor": "Sen. Test (R-6)", "committee": "Finance", "subject": "budget", "url": "https://legiscan.com/OH/bill/SB13/2025"}
]
```

`meta.json`: `{"last_updated": "<today>T12:00:00+00:00", "bill_count": 6, "updated_last_run": 6}`. `changes.json`: `[]`.

- [ ] **Step 2: Serve it**

Run (background): `python -m http.server 8765 --directory <scratchpad>\signed-law-fixture`

- [ ] **Step 3: Verify in the browser** at `http://localhost:8765/ohio-legislation-tracker-LIVE.html`, type filter set to "All legislation" where needed:
  - HB10: all five steps lit; final step reads "Became Law" 📜
  - HB11: four steps lit, "Became Law" pending (reads as on-the-desk)
  - HJR1: all five steps lit; final step "On Ballot" 🗳️
  - SCR2: four-step resolution track, terminal "Adopted Both" lit — unchanged
  - HB12: vetoed banner unchanged
  - Status filter: "Became Law" returns exactly HB10; "On Ballot" exactly HJR1; labels relabel when the type filter changes
  - Sort by Status: SB13 → HB11/SCR2 → HJR1 → HB10 → HB12 ordering respected

- [ ] **Step 4: Fix anything found, re-verify, then commit any fixes**

```powershell
git add ohio-legislation-tracker-LIVE.html
git commit -m "Widget: fixes from browser verification"   # only if fixes were needed
```

---

### Task 7: Migration and deploy

**Files:**
- Delete: `ohio_legislation_data/bill_hashes.json`
- Modify: `.github/workflows/update-legislation.yml:18` (`timeout-minutes: 30` → `45`)

**Interfaces:**
- Consumes: everything above, already committed on `clean`.

- [ ] **Step 1: Pull remote auto-update commits, then stage the migration**

```powershell
git pull origin main
git rm ohio_legislation_data/bill_hashes.json
```

Edit `.github/workflows/update-legislation.yml` line 18: `timeout-minutes: 45` (2,400 sequential API calls with no rate-limit sleep can brush 30 minutes on a slow day; daily runs stay minutes-long).

```powershell
git add .github/workflows/update-legislation.yml
git commit -m "Migrate to type-aware statuses: force full refetch, raise job timeout"
```

- [ ] **Step 2: Deploy and trigger**

```powershell
git push origin clean:main
gh workflow run update-legislation.yml --repo OhioNews/ohio-legislation-tracker
```

- [ ] **Step 3: Watch the run** (`gh run watch <run-id> --repo OhioNews/ohio-legislation-tracker` or poll `gh run list`). Expected: success in roughly 15-30 minutes.

- [ ] **Step 4: Verify the migrated data**

```powershell
git pull origin main
python -c "import json; bills = json.load(open('ohio_legislation_data/bills.json')); from collections import Counter; print(Counter(b['status'] for b in bills)); print('status_code missing:', sum(1 for b in bills if 'status_code' not in b))"
```

Expected: `became-law` roughly 85-103 (the split of the former 103 `passed` HB/SBs), `on-ballot` > 0, `status_code missing: 0`. Then check the feed stayed quiet and the inventory printed:

```powershell
python -c "import json; print(len(json.load(open('ohio_legislation_data/changes.json'))))"
gh run view <run-id> --repo OhioNews/ohio-legislation-tracker --log | Select-String -Pattern "Governor-related" -Context 0,30
```

Expected: changes.json entry count near zero (only bills with genuinely new actions today); the log lists the distinct governor-action strings.

- [ ] **Step 5: Verify live site** — load https://ohionews.github.io/ohio-legislation-tracker/ohio-legislation-tracker-LIVE.html in the browser; spot-check one became-law bill (e.g. SB1: five steps lit) and confirm https://ohionews.github.io/ohio-legislation-tracker/ohio_legislation_data/changes.json now returns 200.

- [ ] **Step 6: Report the governor-string inventory to Scott** — the input for the deferred mechanism-label decision — and update the project memory file.
