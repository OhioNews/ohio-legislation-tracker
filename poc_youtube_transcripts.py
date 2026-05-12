"""
Proof-of-concept: Ohio Channel YouTube transcript scraper
Signal Ohio

Fetches transcripts from the Ohio Channel's YouTube channel and
provides keyword search across all retrieved content.

Usage:
  python3 poc_youtube_transcripts.py --demo          # run offline with sample data
  python3 poc_youtube_transcripts.py --fetch 5       # fetch 5 real videos from YouTube
  python3 poc_youtube_transcripts.py --search "Medicaid"
  python3 poc_youtube_transcripts.py --search "gun" --search "firearm"

Requires: pip install youtube-transcript-api
"""

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime

CHANNEL_ID = "UCporaXCeaOJgZKz7y3C0zbg"  # Ohio Channel on YouTube
TRANSCRIPT_STORE = "ohio_transcripts.json"

# ---------------------------------------------------------------------------
# Sample data for --demo mode (realistic Ohio committee hearing content)
# ---------------------------------------------------------------------------

DEMO_VIDEOS = [
    {
        "video_id": "DEMO001",
        "title": "Ohio Senate Finance Committee 5/7/2025",
        "published": "2025-05-07",
        "url": "https://www.youtube.com/watch?v=DEMO001",
        "transcript": [
            {"start": 12.4,  "duration": 4.1,  "text": "The committee will come to order."},
            {"start": 16.5,  "duration": 5.8,  "text": "Today we consider Senate Bill 142 relating to Medicaid eligibility."},
            {"start": 22.3,  "duration": 6.2,  "text": "Senate Bill 142 would expand Medicaid coverage to approximately 200,000 Ohioans."},
            {"start": 28.5,  "duration": 4.9,  "text": "This includes working families, caregivers, and individuals with disabilities."},
            {"start": 184.0, "duration": 5.5,  "text": "The fiscal note estimates a cost of 340 million dollars in the first biennium."},
            {"start": 189.5, "duration": 6.1,  "text": "Federal matching funds would offset approximately 90 percent of that figure."},
            {"start": 412.8, "duration": 5.2,  "text": "We will now hear from the first proponent witness, Dr. Sarah Chen."},
            {"start": 418.0, "duration": 7.3,  "text": "Thank you. The Medicaid gap leaves roughly 90,000 working adults without any coverage option."},
            {"start": 425.3, "duration": 5.8,  "text": "These are Ohioans who earn too much for traditional Medicaid but cannot afford marketplace plans."},
        ],
    },
    {
        "video_id": "DEMO002",
        "title": "Ohio House Education Committee 5/6/2025",
        "published": "2025-05-06",
        "url": "https://www.youtube.com/watch?v=DEMO002",
        "transcript": [
            {"start": 8.0,   "duration": 4.2,  "text": "Good morning. The House Education Committee is called to order."},
            {"start": 12.2,  "duration": 5.6,  "text": "We are here to take testimony on House Bill 96 regarding school funding."},
            {"start": 17.8,  "duration": 6.0,  "text": "House Bill 96 would revise the evidence-based school funding model."},
            {"start": 310.5, "duration": 5.9,  "text": "Districts in rural Ohio continue to struggle under the current funding formula."},
            {"start": 316.4, "duration": 6.4,  "text": "The per-pupil guarantee has not kept pace with inflation over the past four years."},
            {"start": 580.1, "duration": 5.1,  "text": "We heard from teachers and superintendents who support additional mental health funding."},
            {"start": 585.2, "duration": 6.8,  "text": "Mental health services in schools have become critical since the pandemic."},
        ],
    },
    {
        "video_id": "DEMO003",
        "title": "Ohio Senate Judiciary Committee 5/5/2025",
        "published": "2025-05-05",
        "url": "https://www.youtube.com/watch?v=DEMO003",
        "transcript": [
            {"start": 5.0,   "duration": 3.8,  "text": "The Senate Judiciary Committee will come to order."},
            {"start": 8.8,   "duration": 6.2,  "text": "Today's agenda includes Senate Bill 215 on concealed carry permit requirements."},
            {"start": 15.0,  "duration": 5.5,  "text": "Senate Bill 215 would remove the training requirement for concealed handgun licenses."},
            {"start": 248.0, "duration": 6.1,  "text": "Proponents argue constitutional carry is already the law in 27 other states."},
            {"start": 254.1, "duration": 5.8,  "text": "Law enforcement groups submitted written opposition citing public safety concerns."},
            {"start": 490.3, "duration": 5.4,  "text": "The committee also discussed Senate Bill 198 regarding firearm storage requirements."},
            {"start": 495.7, "duration": 6.7,  "text": "Safe storage legislation is intended to reduce accidental gun deaths among children."},
        ],
    },
]


# ---------------------------------------------------------------------------
# YouTube discovery (real mode)
# ---------------------------------------------------------------------------

def fetch_channel_videos(max_results=10):
    """
    Fetches recent video IDs and titles from the Ohio Channel YouTube feed.
    Uses the public Atom feed — no API key required.
    """
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    print(f"Fetching channel feed: {feed_url}")
    req = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; OhioTranscriptBot/1.0)"},
    )
    resp = urllib.request.urlopen(req, timeout=15)
    xml = resp.read().decode("utf-8")

    ids = re.findall(r"<yt:videoId>([^<]+)</yt:videoId>", xml)
    titles = re.findall(r"<title>([^<]+)</title>", xml)[1:]  # skip channel title
    published = re.findall(r"<published>([^<]+)</published>", xml)

    videos = []
    for vid, title, pub in zip(ids[:max_results], titles[:max_results], published[:max_results]):
        videos.append({
            "video_id": vid,
            "title": title,
            "published": pub[:10],
            "url": f"https://www.youtube.com/watch?v={vid}",
        })

    return videos


def fetch_transcript(video):
    """Fetches transcript for a single video using youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(video["video_id"])
        snippets = [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in transcript.snippets
        ]
        return {**video, "transcript": snippets}
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        print(f"  No transcript available: {e}")
        return None
    except Exception as e:
        print(f"  Error fetching transcript: {e}")
        return None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_store():
    if os.path.exists(TRANSCRIPT_STORE):
        with open(TRANSCRIPT_STORE) as f:
            return json.load(f)
    return []


def save_store(videos):
    with open(TRANSCRIPT_STORE, "w") as f:
        json.dump(videos, f, indent=2)
    print(f"Saved {len(videos)} video(s) to {TRANSCRIPT_STORE}")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def seconds_to_hms(s):
    s = int(s)
    h, m = divmod(s, 3600)
    m, s = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def youtube_deep_link(video_id, start_seconds):
    return f"https://www.youtube.com/watch?v={video_id}&t={int(start_seconds)}s"


def search(videos, keywords):
    """
    Searches transcript segments across all stored videos.
    Returns hits grouped by video, with timestamp deep-links.
    """
    patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords]
    results = []

    for video in videos:
        hits = []
        for seg in video.get("transcript", []):
            if all(p.search(seg["text"]) for p in patterns):
                hits.append({
                    "timestamp": seconds_to_hms(seg["start"]),
                    "start_seconds": seg["start"],
                    "text": seg["text"],
                    "link": youtube_deep_link(video["video_id"], seg["start"]),
                })
        if hits:
            results.append({
                "title": video["title"],
                "date": video.get("published", ""),
                "video_url": video["url"],
                "hits": hits,
            })

    return results


def print_results(keywords, results):
    print(f'\n{"="*60}')
    query_str = " AND ".join(f'"{k}"' for k in keywords)
    print(f"Search: {query_str}")
    print(f'{"="*60}')

    if not results:
        print("No results found.")
        return

    total_hits = sum(len(r["hits"]) for r in results)
    print(f"{total_hits} hit(s) across {len(results)} hearing(s)\n")

    for r in results:
        print(f"  {r['date']}  {r['title']}")
        print(f"  {r['video_url']}")
        for hit in r["hits"]:
            print(f"    [{hit['timestamp']}] {hit['text']}")
            print(f"    → {hit['link']}")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ohio Channel transcript PoC")
    parser.add_argument("--demo", action="store_true", help="Run with sample data (no network)")
    parser.add_argument("--fetch", type=int, metavar="N", help="Fetch N videos from YouTube")
    parser.add_argument("--search", action="append", metavar="KEYWORD", help="Search keyword (repeatable for AND)")
    args = parser.parse_args()

    if args.demo:
        print("Running in demo mode with sample data.\n")
        save_store(DEMO_VIDEOS)
        videos = DEMO_VIDEOS
        if not args.search:
            args.search = ["Medicaid"]

    elif args.fetch:
        print(f"Fetching up to {args.fetch} video(s) from Ohio Channel YouTube...\n")
        channel_videos = fetch_channel_videos(args.fetch)
        print(f"Found {len(channel_videos)} video(s):\n")
        existing = {v["video_id"]: v for v in load_store()}
        new_count = 0
        for v in channel_videos:
            print(f"  {v['published']}  {v['title']}")
            if v["video_id"] in existing:
                print("    (already stored, skipping)")
                continue
            print("    Fetching transcript...", end=" ", flush=True)
            result = fetch_transcript(v)
            if result:
                existing[v["video_id"]] = result
                seg_count = len(result["transcript"])
                print(f"{seg_count} segments")
                new_count += 1
            else:
                print("skipped")
        videos = list(existing.values())
        save_store(videos)
        print(f"\nFetched {new_count} new transcript(s). Store now has {len(videos)} video(s).")

    else:
        videos = load_store()
        if not videos:
            print("No transcripts stored yet. Run with --demo or --fetch N first.")
            return

    if args.search:
        results = search(videos, args.search)
        print_results(args.search, results)


if __name__ == "__main__":
    main()
