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
import os
from datetime import datetime, timedelta

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
    
    try:
        print(f"  \u2192 Calling LegiScan API: {operation}")
        response = requests.get(base_url, params=request_params)
        response.raise_for_status()  # Raise error for bad status codes
        
        data = response.json()
        
        # Check if the API returned an error
        if data.get('status') != 'OK':
            print(f"  \u2717 API Error: {data.get('alert', {}).get('message', 'Unknown error')}")
            return None
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"  \u2717 Network Error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  \u2717 JSON Decode Error: {e}")
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
    # 4=Passed/Signed, 5=Vetoed, 6=Failed/Dead
    status_map = {
        1: 'introduced',
        2: 'passed-chamber',  # Engrossed = passed first chamber
        3: 'passed',          # Enrolled = passed both chambers
        4: 'passed',
        5: 'vetoed',
        6: 'failed'
    }
    status = status_map.get(bill.get('status'), 'introduced')
    # Infer in-committee: introduced bills with a committee assignment are in committee
    if status == 'introduced' and committee:
        status = 'in-committee'
    
    # Get last action
    last_action = 'No recent action'
    last_action_date = bill.get('status_date', '')
    
    if bill.get('history') and len(bill['history']) > 0:
        last_history = bill['history'][-1]
        last_action = last_history.get('action', 'No recent action')
        last_action_date = last_history.get('date', last_action_date)
    
    return {
        'bill_id': bill['bill_id'],
        'number': bill['bill_number'],
        'chamber': chamber,
        'title': bill.get('title', ''),
        'description': bill.get('description', ''),
        'status': status,
        'status_date': bill.get('status_date', ''),
        'last_action': last_action,
        'last_action_date': last_action_date,
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
    if not LEGISCAN_API_KEY:
        print("\n\u2717 ERROR: LEGISCAN_API_KEY environment variable is not set!")
        print("  Add it as a GitHub Actions secret named LEGISCAN_API_KEY.")
        return
    
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"\n\u2713 Created output directory: {OUTPUT_DIR}")
    
    # Get current session
    session_id = get_ohio_session_id()
    if not session_id:
        print("\n\u2717 Failed to get session ID. Exiting.")
        return
    
    # Get master list of bills
    master_list = get_master_list(session_id)
    if not master_list:
        print("\n\u2717 Failed to get master list. Exiting.")
        return
    
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
        print("\nDone! No updates needed.")
        return
    
    # Fetch detailed bill information
    print(f"\n5. Fetching details for {len(bills_to_fetch)} bills...")
    print("   (This may take a minute...)")
    
    bills_for_widget = []
    all_hearings = []
    
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
            
            print(" \u2713")
        else:
            print(" \u2717")
    
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
