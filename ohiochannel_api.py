"""
Ohio Channel public API client - Signal Ohio Statehouse Transcripts

Unauthenticated JSON API discovered July 2026. GET only (POST returns 405).
Politeness is enforced here so no caller can forget it: 1 request/second,
identifying User-Agent, bounded retries.
"""
import json
import time
import urllib.parse
import urllib.request

BASE = "https://www.ohiochannel.org/api/public"
USER_AGENT = "ohio-legislation-tracker (scott@signalohio.org)"
THROTTLE_SECONDS = 1.0
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

_last_request = 0.0


def _throttle():
    global _last_request
    wait = THROTTLE_SECONDS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def fetch_json(url):
    """Throttled GET returning parsed JSON. Raises RuntimeError after MAX_RETRIES."""
    last_err = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'},
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read())
        except Exception as e:  # network, HTTP, JSON — all retryable here
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API call failed after {MAX_RETRIES} attempts: {url}: {last_err}")


def list_programs(series_id, start=1, page_size=50):
    q = urllib.parse.urlencode({
        'series': series_id,
        'pageSize': page_size,
        'sort': 'releaseDate',
        'direction': 'desc',
        'start': start,
    })
    return fetch_json(f"{BASE}/programming/programs?{q}")


def get_captions(program_id):
    data = fetch_json(f"{BASE}/programming/captions/findByProgramId?programId={program_id}")
    return data.get('records') or []


def get_markers(program_id):
    data = fetch_json(f"{BASE}/programming/markers/findByProgramId?programId={program_id}")
    return data.get('records') or []


def get_series():
    return fetch_json(f"{BASE}/programming/series")
