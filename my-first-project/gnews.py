#!/usr/bin/env python3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import argparse
import sys
import os
import platform
import datetime

# Enable ANSI escape sequences on Windows
if platform.system() == 'Windows':
    os.system('')

# Force UTF-8 stdout if supported to prevent Unicode encoding errors on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Colors
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_TITLE = "\033[1;37m"  # Bold White
COLOR_SOURCE = "\033[1;32m" # Bold Green
COLOR_DATE = "\033[36m"     # Cyan
COLOR_LINK = "\033[4;34m"   # Underline Blue
COLOR_INDEX = "\033[1;33m"  # Bold Yellow
COLOR_HEADER = "\033[1;35m" # Bold Magenta

TOPICS = {
    'world': 'WORLD',
    'nation': 'NATION',
    'business': 'BUSINESS',
    'technology': 'TECHNOLOGY',
    'entertainment': 'ENTERTAINMENT',
    'sports': 'SPORTS',
    'science': 'SCIENCE',
    'health': 'HEALTH'
}

def get_feed_url(topic=None, search=None):
    if search:
        query = urllib.parse.quote(search)
        return f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    elif topic:
        topic_lower = topic.lower()
        if topic_lower in TOPICS:
            topic_id = TOPICS[topic_lower]
            return f"https://news.google.com/rss/headlines/section/topic/{topic_id}?hl=en-US&gl=US&ceid=US:en"
        else:
            print(f"Unknown topic '{topic}'. Available topics: {', '.join(TOPICS.keys())}")
            sys.exit(1)
    else:
        return "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

def fetch_rss(url):
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        print(f"Error fetching news feed: {e}")
        sys.exit(1)

def parse_rss(xml_data):
    try:
        root = ET.fromstring(xml_data)
        items = []
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else 'No Title'
            link = item.find('link').text if item.find('link') is not None else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
            
            # Source is usually within <source> tag or in title (Google News appends " - Source Name" to title)
            source_tag = item.find('source')
            source = source_tag.text if source_tag is not None else ''
            
            # Clean title if it contains the source at the end
            clean_title = title
            if source and title.endswith(f" - {source}"):
                clean_title = title[:-len(f" - {source}")]
                
            items.append({
                'title': clean_title,
                'source': source,
                'link': link,
                'pub_date': pub_date
            })
        return items
    except Exception as e:
        print(f"Error parsing feed XML: {e}")
        sys.exit(1)

def display_news(items, limit):
    if not items:
        print("No articles found.")
        return
    
    count = min(len(items), limit)
    print(f"\n{COLOR_HEADER}=== Google News - Latest Articles (showing {count}) ==={COLOR_RESET}\n")
    
    for i in range(count):
        item = items[i]
        date_str = item['pub_date']
        try:
            # Parse RSS pubDate e.g., "Mon, 15 Jun 2026 21:00:00 GMT"
            dt = datetime.datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
            date_str = dt.strftime("%b %d, %Y %I:%M %p")
        except Exception:
            pass
        
        print(f"{COLOR_INDEX}[{i+1}]{COLOR_RESET} {COLOR_TITLE}{item['title']}{COLOR_RESET}")
        print(f"    Source: {COLOR_SOURCE}{item['source']}{COLOR_RESET} | Date: {COLOR_DATE}{date_str}{COLOR_RESET}")
        print(f"    Link:   {COLOR_LINK}{item['link']}{COLOR_RESET}\n")

def main():
    parser = argparse.ArgumentParser(description="Fetch and display news from Google News RSS feeds.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-t", "--topic", help=f"Filter news by topic. Available: {', '.join(TOPICS.keys())}")
    group.add_argument("-s", "--search", help="Search news articles by keyword")
    parser.add_argument("-l", "--limit", type=int, default=10, help="Limit number of displayed news (default: 10)")
    
    args = parser.parse_args()
    
    url = get_feed_url(topic=args.topic, search=args.search)
    
    title_context = "Top Stories"
    if args.search:
        title_context = f"Search results for '{args.search}'"
    elif args.topic:
        title_context = f"Topic: {args.topic.upper()}"
        
    print(f"Fetching news from Google ({title_context})...")
    xml_data = fetch_rss(url)
    items = parse_rss(xml_data)
    display_news(items, args.limit)

if __name__ == "__main__":
    main()
