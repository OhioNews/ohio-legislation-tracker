"""
Proof-of-concept: Ohio Channel caption scraper
Tests whether VTT caption files are retrievable from ohiochannel.org

Three things to validate:
  1. Can we find the VTT URL from a video page?
  2. Can we download the VTT content?
  3. Can we discover video pages from a committee collection?
"""

import re
import sys
import time
from playwright.sync_api import sync_playwright

# A real committee hearing to test against
TEST_VIDEO_URL = "https://www.ohiochannel.org/video/ohio-senate-finance-committee-5-7-2025"
TEST_COLLECTION_URL = "https://www.ohiochannel.org/collections/ohio-senate-finance-committee"


def parse_vtt(vtt_text):
    """Strip VTT markup and return plain-text lines with timestamps."""
    segments = []
    lines = vtt_text.splitlines()
    i = 0
    while i < len(lines):
        # Look for a timestamp line: 00:00:00.000 --> 00:00:00.000
        if "-->" in lines[i]:
            timestamp = lines[i].strip()
            text_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                # Strip VTT tags like <c>, <00:00:00.000>, etc.
                clean = re.sub(r"<[^>]+>", "", lines[i]).strip()
                if clean:
                    text_lines.append(clean)
                i += 1
            if text_lines:
                segments.append({"timestamp": timestamp, "text": " ".join(text_lines)})
        else:
            i += 1
    return segments


def test_caption_retrieval(page, video_url):
    """
    Load a video page and capture the VTT file.
    Uses two strategies:
      A) Intercept the .vtt network request directly
      B) Parse the <track> element from the DOM
    """
    print(f"\n{'='*60}")
    print(f"Testing: {video_url}")
    print("="*60)

    captured_vtt = {"url": None, "content": None}

    def handle_response(response):
        if ".vtt" in response.url and response.status == 200:
            captured_vtt["url"] = response.url
            try:
                captured_vtt["content"] = response.text()
                print(f"  [Network intercept] Captured VTT: {response.url}")
            except Exception as e:
                print(f"  [Network intercept] Found VTT URL but couldn't read body: {e}")

    page.on("response", handle_response)

    print(f"\nLoading page...")
    try:
        page.goto(video_url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"  Page load warning (may still be usable): {e}")

    # Give the video player a moment to initialize
    time.sleep(3)

    # Strategy B: look for <track> element in the DOM
    track_url = page.evaluate("""
        () => {
            const track = document.querySelector('track[kind="captions"], track[kind="subtitles"], track');
            return track ? track.src : null;
        }
    """)

    if track_url:
        print(f"  [DOM] Found <track> src: {track_url}")
        if not captured_vtt["url"]:
            captured_vtt["url"] = track_url

    # Strategy C: look for VTT URLs buried in page source / script tags
    if not captured_vtt["url"]:
        content = page.content()
        vtt_matches = re.findall(r'https?://[^\s\'"]+\.vtt', content)
        if vtt_matches:
            print(f"  [Source scan] Found VTT URLs in page source:")
            for url in vtt_matches:
                print(f"    {url}")
            captured_vtt["url"] = vtt_matches[0]

    if not captured_vtt["url"]:
        print("  RESULT: No VTT URL found by any strategy.")
        return None

    # If we have the URL but not the content, fetch it now
    if not captured_vtt["content"]:
        print(f"\n  Fetching VTT content from: {captured_vtt['url']}")
        try:
            response = page.request.get(captured_vtt["url"])
            if response.status == 200:
                captured_vtt["content"] = response.text()
                print(f"  HTTP {response.status} — downloaded {len(captured_vtt['content'])} bytes")
            else:
                print(f"  HTTP {response.status} — fetch failed")
        except Exception as e:
            print(f"  Fetch error: {e}")

    if not captured_vtt["content"]:
        print("  RESULT: Found VTT URL but could not retrieve content.")
        return {"url": captured_vtt["url"], "segments": []}

    # Parse the VTT
    segments = parse_vtt(captured_vtt["content"])
    print(f"\n  RESULT: Parsed {len(segments)} caption segments")

    if segments:
        print("\n  --- First 5 segments ---")
        for seg in segments[:5]:
            print(f"  [{seg['timestamp']}]")
            print(f"  {seg['text']}\n")
        print("  --- Last 3 segments ---")
        for seg in segments[-3:]:
            print(f"  [{seg['timestamp']}]")
            print(f"  {seg['text']}\n")

    return {"url": captured_vtt["url"], "segments": segments}


def test_collection_discovery(page, collection_url):
    """
    Load a committee collection page and extract video links.
    Tests whether we can enumerate available hearings.
    """
    print(f"\n{'='*60}")
    print(f"Testing collection discovery: {collection_url}")
    print("="*60)

    try:
        page.goto(collection_url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"  Page load warning: {e}")

    time.sleep(2)

    # Look for video links on the collection page
    video_links = page.evaluate("""
        () => {
            const links = Array.from(document.querySelectorAll('a[href*="/video/"]'));
            return links.map(a => ({
                href: a.href,
                text: a.textContent.trim().substring(0, 80)
            }));
        }
    """)

    # Deduplicate
    seen = set()
    unique_links = []
    for link in video_links:
        if link["href"] not in seen:
            seen.add(link["href"])
            unique_links.append(link)

    print(f"\n  Found {len(unique_links)} video links:")
    for link in unique_links[:10]:
        print(f"    {link['text']}")
        print(f"    → {link['href']}")
    if len(unique_links) > 10:
        print(f"    ... and {len(unique_links) - 10} more")

    return unique_links


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Test 1: Can we get captions from a specific video?
        result = test_caption_retrieval(page, TEST_VIDEO_URL)

        # Test 2: Can we discover videos from a collection?
        videos = test_collection_discovery(page, TEST_COLLECTION_URL)

        # Test 3: If collection gave us video URLs, try one of those too
        if videos and result is None:
            print("\n\nPrimary test video not found — trying first video from collection...")
            test_caption_retrieval(page, videos[0]["href"])

        browser.close()

    print("\n" + "="*60)
    print("Proof-of-concept complete.")
    print("="*60)


if __name__ == "__main__":
    main()
