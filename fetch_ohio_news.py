"""
Ohio News Aggregator - RSS Feed Fetcher
Signal Ohio
"""

import feedparser
import json
import os
import re
from datetime import datetime, timezone, timedelta

FEEDS = [
    {"name": "Ohio Capital Journal",        "url": "https://ohiocapitaljournal.com/feed/"},
    {"name": "Toledo Blade",                "url": "https://www.toledoblade.com/rss"},
    {"name": "Richland Source",             "url": "https://www.richlandsource.com/feed/"},
    {"name": "WCMH / NBC4i",               "url": "https://www.nbc4i.com/feed/"},
    {"name": "Spectrum News 1",             "url": "https://spectrumnews1.com/oh/columbus/rss"},
    {"name": "The Rooster",                 "url": "https://www.rooster.info/feed"},
    {"name": "Buckeye Flame",              "url": "https://thebuckeyeflame.com/feed/"},
    {"name": "WCPO",                        "url": "https://www.wcpo.com/news/state/state-ohio.rss"},
    {"name": "Google News: Ohio Statehouse","url": "https://news.google.com/rss/search?q=ohio+statehouse&hl=en-US&gl=US&ceid=US:en"},
]

HOURS_BACK = 48
OUTPUT_DIR = "ohio_news_data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "news.json")


def parse_date(entry):
    for attr in ('published_parsed', 'updated_parsed'):
        val = getattr(entry, attr, None)
        if val:
            return datetime(*val[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()


def fetch_feed(feed):
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    try:
        d = feedparser.parse(feed['url'])
        for entry in d.entries:
            pub_date = parse_date(entry)
            if pub_date < cutoff:
                continue
            title = strip_html(entry.get('title', '')).strip()
            link  = entry.get('link', '').strip()
            if not title or not link:
                continue
            items.append({
                'title':    title,
                'link':     link,
                'pub_date': pub_date.isoformat(),
                'source':   feed['name'],
            })
        print(f"  {feed['name']}: {len(items)} items")
    except Exception as e:
        print(f"  ERROR {feed['name']}: {e}")
    return items


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_items = []
    seen_links = set()

    for feed in FEEDS:
        for item in fetch_feed(feed):
            if item['link'] not in seen_links:
                seen_links.add(item['link'])
                all_items.append(item)

    all_items.sort(key=lambda x: x['pub_date'], reverse=True)

    output = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'item_count':   len(all_items),
        'items':        all_items,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(all_items)} items to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
