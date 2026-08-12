"""
Ohio Legislation Tracker - LegiScan Data Fetcher
Signal Ohio

This script fetches Ohio legislative data from LegiScan API and saves it
in a format your widgets can read. It includes hash checking to minimize
API usage and only fetches bills that have actually changed.

IMPORTANT: Set the LEGISCAN_API_KEY GitHub Actions secret before running!
"""

import requests
import json
import re
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# ============================================================================
# CONFIGURATION - EDIT THIS SECTION
# ============================================================================

# Put your LegiScan API key here (between the quotes)
# Or set it as an environment variable LEGISCAN_API_KEY for GitHub Actions
LEGISCAN_API_KEY = os.environ.get('LEGISCAN_API_KEY', "")

# Output file paths (where the data will be saved)
OUTPUT_DIR = "ohio_legislation_data"
BILLS_OUTPUT = os.path.join(OUTPUT_DIR, "bills.json")
HEARINGS_OUTPUT = os.path.join(OUTPUT_DIR, "hearings.json")
HASH_STORAGE = os.path.join(OUTPUT_DIR, "bill_hashes.json")
META_OUTPUT = os.path.join(OUTPUT_DIR, "meta.json")
CHANGES_OUTPUT = os.path.join(OUTPUT_DIR, "changes.json")

# How many days of change history to keep in changes.json
CHANGES_KEEP_DAYS = 14

# Seconds before an API call is abandoned (a hung call would otherwise
# hang the GitHub Actions job until its own timeout)
REQUEST_TIMEOUT = 30

# LegiScan intermittently refuses connections for a few seconds at a time.
# A single attempt is why a whole run dies on a momentary blip, so retry
# network failures with a widening pause: 2s, then 4s.
MAX_ATTEMPTS = 3
RETRY_BASE_WAIT = 2

# How many days ahead to show committee hearings (14 = 2 weeks)
HEARING_DAYS_AHEAD = 14

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def call_legiscan_api(operation, params=None):
    """
    Makes a call to the LegiScan API
    
    Args:
        operation: The API operation (e.g., 'getMasterListRaw', 'getBill')
        params: Dictionary of parameters for the API call
    
    Returns:
        The JSON response from the API, or None if there was an error
    """
    base_url = "https://api.legiscan.com/"
    
    # Build the request parameters
    request_params = {
        'key': LEGISCAN_API_KEY,
        'op': operation
    }
    
    # Add any additional parameters
    if params:
        request_params.update(params)
    
    print(f"  \u2192 Calling LegiScan API: {operation}")

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(base_url, params=request_params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()  # Raise error for bad status codes

            data = response.json()

            # Check if the API returned an error. This is LegiScan answering,
            # not the network failing, so retrying won't change the answer.
            if data.get('status') != 'OK':
                print(f"  \u2717 API Error: {data.get('alert', {}).get('message', 'Unknown error')}")
                return None

            if attempt > 1:
                print(f"  \u2713 Succeeded on attempt {attempt}")

            return data

        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            last_error = e

            if attempt < MAX_ATTEMPTS:
                wait = RETRY_BASE_WAIT * (2 ** (attempt - 1))
                print(f"  \u26a0 {type(e).__name__} on attempt {attempt} of {MAX_ATTEMPTS}; retrying in {wait}s")
                time.sleep(wait)

    print(f"  \u2717 Failed after {MAX_ATTEMPTS} attempts: {last_error}")
    return None


def load_stored_hashes():
    """
    Loads previously stored bill hashes from file
    
    Returns:
        Dictionary of bill_id -> hash, or empty dict if file doesn't exist
    """
    if os.path.exists(HASH_STORAGE):
        with open(HASH_STORAGE, 'r') as f:
            return json.load(f)
    return {}


def write_meta(bill_count, updated_count):
    """
    Writes a freshness stamp so the widget (and a human checking the repo)
    can tell when the pipeline last ran successfully — even on days when
    no bills changed.
    """
    meta = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'bill_count': bill_count,
        'updated_last_run': updated_count
    }
    with open(META_OUTPUT, 'w') as f:
        json.dump(meta, f, indent=2)


def build_change_entries(existing_bills, new_bills, run_date):
    """
    Diffs freshly fetched bills against their previous records to produce
    'what moved' entries for the daily monitoring feed.

    A bill whose hash changed but whose last action is identical (e.g. a
    new text version was uploaded, or only our status mapping changed) is
    treated as noise and skipped.
    """
    entries = []
    for b in new_bills:
        old = existing_bills.get(b['bill_id'])
        # A refetch that brought no new action is noise — even if the
        # derived status string changed (that only happens when our own
        # mapping changed; real status changes always add a history action)
        if old and \
           old.get('last_action') == b.get('last_action') and \
           old.get('last_action_date') == b.get('last_action_date'):
            continue
        # Migration guard: records written before effective-date handling stored
        # the scheduled 'Effective' row as the last action, dated in the future.
        # Reformatting an already-enacted bill to its real signing action is
        # bookkeeping, not news, so long as it took no action past that date.
        if old and is_effective_action(old.get('last_action')) and \
           b.get('last_action_date', '') <= old.get('last_action_date', ''):
            continue
        entries.append({
            'run_date': run_date,
            'number': b['number'],
            'title': b.get('title', ''),
            'status': b.get('status'),
            'prev_status': old.get('status') if old else None,
            'is_new': old is None,
            'last_action': b.get('last_action', ''),
            'last_action_date': b.get('last_action_date', ''),
            'url': b.get('url', '')
        })
    return entries


def update_changes_feed(new_entries):
    """
    Prepends new change entries to changes.json and prunes anything older
    than CHANGES_KEEP_DAYS.
    """
    old_entries = []
    if os.path.exists(CHANGES_OUTPUT):
        try:
            with open(CHANGES_OUTPUT) as f:
                old_entries = json.load(f)
        except json.JSONDecodeError:
            old_entries = []

    cutoff = (datetime.now() - timedelta(days=CHANGES_KEEP_DAYS)).strftime('%Y-%m-%d')
    kept = [e for e in old_entries if e.get('run_date', '') >= cutoff]

    merged = new_entries + kept
    with open(CHANGES_OUTPUT, 'w') as f:
        json.dump(merged, f, indent=2)
    return merged


def count_existing_bills():
    """Returns the number of bills currently in the output file."""
    if os.path.exists(BILLS_OUTPUT):
        try:
            with open(BILLS_OUTPUT) as f:
                return len(json.load(f))
        except json.JSONDecodeError:
            pass
    return 0


def save_hashes(hashes):
    """
    Saves bill hashes to file for next time
    
    Args:
        hashes: Dictionary of bill_id -> hash to save
    """
    with open(HASH_STORAGE, 'w') as f:
        json.dump(hashes, f, indent=2)


def get_ohio_session_id():
    """
    Gets the current Ohio legislative session ID
    
    Returns:
        The session_id for the current Ohio session, or None if not found
    """
    print("\n1. Finding current Ohio legislative session...")
    
    data = call_legiscan_api('getSessionList', {'state': 'OH'})
    
    if not data or 'sessions' not in data:
        print("  \u2717 Could not retrieve session list")
        return None
    
    # Find the current (non-prior) session
    for session in data['sessions']:
        if session.get('prior') == 0:
            session_id = session['session_id']
            session_name = session['session_name']
            print(f"  \u2713 Found current session: {session_name} (ID: {session_id})")
            return session_id
    
    print("  \u2717 Could not find current Ohio session")
    return None


def get_master_list(session_id):
    """
    Gets the master list of bills with their change hashes
    
    Args:
        session_id: The Ohio legislative session ID
    
    Returns:
        Dictionary of bill data with bill_id as keys
    """
    print("\n2. Fetching master list of Ohio bills...")
    
    data = call_legiscan_api('getMasterListRaw', {'id': session_id})
    
    if not data or 'masterlist' not in data:
        print("  \u2717 Could not retrieve master list")
        return {}
    
    bills = data['masterlist']
    print(f"  \u2713 Found {len(bills)} bills in current session")
    
    return bills


def get_bill_details(bill_id):
    """
    Gets full details for a specific bill
    
    Args:
        bill_id: The bill ID to fetch
    
    Returns:
        Dictionary of bill details, or None if error
    """
    data = call_legiscan_api('getBill', {'id': bill_id})
    
    if not data or 'bill' not in data:
        return None
    
    return data['bill']


def extract_hearing_info(bill):
    """
    Extracts hearing/calendar information from a bill
    
    Args:
        bill: The bill data dictionary
    
    Returns:
        List of hearing dictionaries
    """
    hearings = []
    
    if 'calendar' not in bill or not bill['calendar']:
        return hearings
    
    # Get current date and cutoff date
    today = datetime.now().date()
    cutoff_date = today + timedelta(days=HEARING_DAYS_AHEAD)
    
    for event in bill['calendar']:
        # Parse the event date
        try:
            event_date = datetime.strptime(event['date'], '%Y-%m-%d').date()
        except:
            continue
        
        # Only include upcoming hearings within our window
        if event_date < today or event_date > cutoff_date:
            continue
        
        # Determine chamber from bill number
        chamber = 'house' if bill['bill_number'].startswith('H') else 'senate'
        
        # Extract committee info
        committee = 'Unknown'
        committee_short = 'unknown'
        if bill.get('committee'):
            committee = bill['committee'].get('name', 'Unknown')
            committee_short = committee.lower().replace(' ', '-')
        
        hearing = {
            'id': f"{bill['bill_id']}_{event['date']}",
            'date': event['date'],
            'time': event.get('time', ''),
            'chamber': chamber,
            'committee': committee_short,
            'committee_full': committee,
            'type': event.get('type', 'Hearing'),
            'location': event.get('location', ''),
            'description': event.get('description', ''),
            'bills': [{
                'number': bill['bill_number'],
                'title': bill.get('title', ''),
                'url': bill.get('url', '')
            }]
        }
        
        hearings.append(hearing)
    
    return hearings


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


# \bsign (not bare "sign") so "Assigned to committee" doesn't match
GOVERNOR_ACTION_RE = re.compile(r'governor|\bsign|veto|override', re.IGNORECASE)


def is_effective_action(action):
    """True for LegiScan's 'Effective ...' history rows.

    Those rows log a law's effective date, which in Ohio is typically ~90 days
    after enactment. That scheduled date is not a legislative action, so it must
    not become a bill's last action or drive 'most recent activity' sorting.
    """
    return (action or '').strip().lower().startswith('effective')


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


def format_bill_for_widget(bill):
    """
    Formats a bill into the structure the widget expects
    
    Args:
        bill: The bill data from LegiScan
    
    Returns:
        Dictionary formatted for the widget
    """
    # Determine chamber
    chamber = 'house' if bill['bill_number'].startswith('H') else 'senate'
    
    # Get primary sponsor
    sponsor = 'Unknown'
    if bill.get('sponsors') and len(bill['sponsors']) > 0:
        sponsor_data = bill['sponsors'][0]
        name = sponsor_data.get('name', 'Unknown')
        party = sponsor_data.get('party', '')
        role = sponsor_data.get('role', '')
        district = sponsor_data.get('district', '')
        
        if party and role:
            sponsor = f"{role}. {name} ({party}-{district})"
        else:
            sponsor = name
    
    # Get committee
    committee = None
    if bill.get('committee'):
        committee = bill['committee'].get('name')
    
    # Get subject
    subject = 'general'
    if bill.get('subjects') and len(bill['subjects']) > 0:
        subject_name = bill['subjects'][0]['subject_name'].lower()
        # Map to our categories
        if 'education' in subject_name:
            subject = 'education'
        elif 'health' in subject_name or 'medical' in subject_name:
            subject = 'healthcare'
        elif 'tax' in subject_name or 'budget' in subject_name or 'fiscal' in subject_name:
            subject = 'budget'
        elif 'environment' in subject_name or 'energy' in subject_name:
            subject = 'environment'
        elif 'transport' in subject_name:
            subject = 'transportation'
        elif 'criminal' in subject_name or 'crime' in subject_name:
            subject = 'criminal-justice'
    
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
    # Infer in-committee: introduced bills with a committee assignment are in committee
    if status == 'introduced' and committee:
        status = 'in-committee'
    
    # Get last action. A law's final history row is its scheduled 'Effective'
    # date, not a real action — so pull the effective date out separately and
    # let the newest *non-effective* row stand as the last action. This keeps a
    # bill signed months ago from floating to the top of "most recent activity"
    # on a future effective date.
    last_action = 'No recent action'
    last_action_date = bill.get('status_date', '')
    effective_date = ''
    history = bill.get('history') or []

    for event in reversed(history):
        if is_effective_action(event.get('action')):
            effective_date = event.get('date', '')
            break

    for event in reversed(history):
        if not is_effective_action(event.get('action')):
            last_action = event.get('action', 'No recent action')
            last_action_date = event.get('date', last_action_date)
            break

    return {
        'bill_id': bill['bill_id'],
        'number': bill['bill_number'],
        'chamber': chamber,
        'title': bill.get('title', ''),
        'description': bill.get('description', ''),
        'status': status,
        'status_code': status_code,
        'status_date': bill.get('status_date', ''),
        'last_action': last_action,
        'last_action_date': last_action_date,
        'effective_date': effective_date,
        'sponsor': sponsor,
        'committee': committee,
        'subject': subject,
        'url': bill.get('url', '')
    }


def merge_hearings(hearings_list):
    """
    Merges hearings that are for the same committee meeting
    
    Args:
        hearings_list: List of individual hearing dictionaries
    
    Returns:
        List of merged hearings
    """
    # Group by date + time + committee
    grouped = {}
    
    for hearing in hearings_list:
        key = f"{hearing['date']}_{hearing['time']}_{hearing['committee']}"
        
        if key not in grouped:
            grouped[key] = hearing
        else:
            # Merge bills
            grouped[key]['bills'].extend(hearing['bills'])
    
    return list(grouped.values())


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main function that orchestrates the data fetching process
    """
    print("=" * 70)
    print("Ohio Legislation Tracker - Data Fetch")
    print("Signal Ohio")
    print("=" * 70)
    
    # Check if API key is set
    # Fatal errors exit nonzero so GitHub Actions fails the run and
    # notifies \u2014 a broken pipeline must never look like a green checkmark.
    if not LEGISCAN_API_KEY:
        print("\n\u2717 ERROR: LEGISCAN_API_KEY environment variable is not set!")
        print("  Add it as a GitHub Actions secret named LEGISCAN_API_KEY.")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"\n\u2713 Created output directory: {OUTPUT_DIR}")
    
    # Get current session
    session_id = get_ohio_session_id()
    if not session_id:
        print("\n\u2717 Failed to get session ID. Exiting.")
        sys.exit(1)
    
    # Get master list of bills
    master_list = get_master_list(session_id)
    if not master_list:
        print("\n\u2717 Failed to get master list. Exiting.")
        sys.exit(1)
    
    # Load stored hashes
    stored_hashes = load_stored_hashes()
    print(f"\n3. Loaded {len(stored_hashes)} previously stored bill hashes")
    
    # Determine which bills need to be fetched
    bills_to_fetch = []
    new_hashes = {}
    
    for bill_data in master_list.values():
        # Skip entries that don't have the expected structure
        if not isinstance(bill_data, dict) or 'bill_id' not in bill_data:
            continue
            
        bill_id = str(bill_data['bill_id'])
        current_hash = bill_data['change_hash']
        
        new_hashes[bill_id] = current_hash
        
        # Check if this bill is new or has changed
        if bill_id not in stored_hashes or stored_hashes[bill_id] != current_hash:
            bills_to_fetch.append(bill_id)
    
    print(f"\n4. Identified {len(bills_to_fetch)} bills that are new or have changed")
    
    if len(bills_to_fetch) == 0:
        print("\n\u2713 No bills have changed since last fetch. Data is up to date!")
        write_meta(count_existing_bills(), 0)
        print("\nDone! No updates needed. Freshness stamp written.")
        return
    
    # Fetch detailed bill information
    print(f"\n5. Fetching details for {len(bills_to_fetch)} bills...")
    print("   (This may take a minute...)")
    
    bills_for_widget = []
    all_hearings = []
    failed_count = 0
    governor_actions = set()

    for i, bill_id in enumerate(bills_to_fetch, 1):
        print(f"   [{i}/{len(bills_to_fetch)}] Fetching bill {bill_id}...", end='')

        bill = get_bill_details(bill_id)

        if bill:
            # Format for bill tracker widget
            formatted_bill = format_bill_for_widget(bill)
            bills_for_widget.append(formatted_bill)

            # Extract hearing information
            hearings = extract_hearing_info(bill)
            all_hearings.extend(hearings)

            governor_actions |= governor_actions_in(bill)

            print(" \u2713")
        else:
            # Roll the hash back to its previous value so this bill still
            # counts as changed and gets retried on the next run
            failed_count += 1
            if bill_id in stored_hashes:
                new_hashes[bill_id] = stored_hashes[bill_id]
            else:
                new_hashes.pop(bill_id, None)
            print(" \u2717 (will retry next run)")

    if failed_count == len(bills_to_fetch):
        print(f"\n\u2717 All {failed_count} bill fetches failed \u2014 API is likely down or key is invalid.")
        sys.exit(1)

    if failed_count:
        print(f"\n\u26a0 {failed_count} of {len(bills_to_fetch)} bill fetches failed; they will retry next run.")
    
    # Merge duplicate hearings
    merged_hearings = merge_hearings(all_hearings)
    
    print(f"\n6. Saving data to files...")

    # Merge newly fetched bills with existing bills so we never lose data
    # Load existing bills (keyed by bill_id for fast lookup)
    existing_bills = {}
    if os.path.exists(BILLS_OUTPUT):
        try:
            with open(BILLS_OUTPUT) as f:
                for b in json.load(f):
                    existing_bills[b['bill_id']] = b
        except (json.JSONDecodeError, KeyError):
            pass  # Start fresh if file is corrupt

    # Diff against previous records for the daily changes feed
    # (must happen before the overwrite below)
    run_date = datetime.now().strftime('%Y-%m-%d')
    change_entries = build_change_entries(existing_bills, bills_for_widget, run_date)

    # Overwrite changed/new bills; preserve everything else
    for b in bills_for_widget:
        existing_bills[b['bill_id']] = b

    all_bills = sorted(existing_bills.values(), key=lambda b: b.get('bill_id', 0))

    # Save bills data
    with open(BILLS_OUTPUT, 'w') as f:
        json.dump(all_bills, f, indent=2)
    print(f"   \u2713 Saved {len(all_bills)} bills to {BILLS_OUTPUT} ({len(bills_for_widget)} updated)")
    
    # Save hearings data
    with open(HEARINGS_OUTPUT, 'w') as f:
        json.dump(merged_hearings, f, indent=2)
    print(f"   \u2713 Saved {len(merged_hearings)} hearings to {HEARINGS_OUTPUT}")
    
    # Save updated hashes
    save_hashes(new_hashes)
    print(f"   \u2713 Saved {len(new_hashes)} bill hashes to {HASH_STORAGE}")

    # Save freshness stamp
    write_meta(len(all_bills), len(bills_for_widget))
    print(f"   \u2713 Saved freshness stamp to {META_OUTPUT}")

    # Save the daily changes feed
    all_changes = update_changes_feed(change_entries)
    print(f"   \u2713 Saved changes feed to {CHANGES_OUTPUT} ({len(change_entries)} new, {len(all_changes)} total)")

    if governor_actions:
        print(f"\n7. Governor-related action strings seen this run ({len(governor_actions)}):")
        for action in sorted(governor_actions):
            print(f"   \u2022 {action}")
    
    print("\n" + "=" * 70)
    print("SUCCESS! Data fetch complete.")
    print("=" * 70)
    print(f"\nYour widgets can now read from:")
    print(f"  \u2022 {BILLS_OUTPUT}")
    print(f"  \u2022 {HEARINGS_OUTPUT}")
    print(f"\nNext run will only fetch bills that have changed.")
    print("Run this script daily to keep data fresh!")


if __name__ == "__main__":
    main()
