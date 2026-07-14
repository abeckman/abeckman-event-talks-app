from flask import Flask, jsonify, render_template, request
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

app = Flask(__name__)

FEED_URL = "https://docs.cloud.google.com/feeds/bigquery-release-notes.xml"

# In-memory cache
CACHE = {
    "data": None,
    "last_fetched": 0,
    "status": "idle",
    "warning_message": None
}
CACHE_DURATION = 600  # 10 minutes (600 seconds)

def create_release_item(entry_id, date, raw_date, link, type_str, blocks):
    # Construct html content
    content_html = ""
    for block in blocks:
        content_html += str(block)
    
    # Construct plain text content for Twitter/X sharing
    soup_copy = BeautifulSoup(content_html, 'html.parser')
    
    # Format anchor tags as "Text (URL)"
    for a in soup_copy.find_all('a'):
        href = a.get('href', '')
        if href.startswith('/'):
            href = 'https://cloud.google.com' + href
        a.replace_with(f"{a.get_text()} ({href})")
        
    text_content = soup_copy.get_text().strip()
    # Normalize whitespaces
    text_content = re.sub(r'\s+', ' ', text_content)
    
    return {
        "id": entry_id,
        "date": date,
        "raw_date": raw_date,
        "link": link,
        "type": type_str,
        "content_html": content_html.strip(),
        "content_text": text_content
    }

def fetch_and_parse_releases():
    response = requests.get(FEED_URL, timeout=10)
    response.raise_for_status()
    
    # Parse the Atom XML feed
    root = ET.fromstring(response.content)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    
    releases = []
    
    for entry in root.findall('atom:entry', ns):
        title = entry.find('atom:title', ns).text  # e.g., "July 13, 2026"
        entry_id = entry.find('atom:id', ns).text
        updated = entry.find('atom:updated', ns).text  # ISO format date
        
        # Link to details
        link_elem = entry.find("atom:link[@rel='alternate']", ns)
        link = link_elem.attrib.get('href') if link_elem is not None else "https://cloud.google.com/bigquery/docs/release-notes"
        if link.startswith('https://docs.google.com') or link.startswith('https://docs.cloud.google.com'):
            # Convert to user-friendly cloud.google.com format
            link = link.replace('docs.cloud.google.com', 'cloud.google.com').replace('docs.google.com', 'cloud.google.com')
            
        content_elem = entry.find('atom:content', ns)
        if content_elem is None or not content_elem.text:
            continue
            
        content_html = content_elem.text
        soup = BeautifulSoup(content_html, 'html.parser')
        
        current_type = "Update"
        current_blocks = []
        item_index = 0
        
        # Walk through the child elements of the feed content
        for child in soup.contents:
            if child.name == 'h3':
                # Save the accumulated block as a release item
                if current_blocks:
                    releases.append(create_release_item(
                        entry_id=f"{entry_id}_{item_index}",
                        date=title,
                        raw_date=updated,
                        link=link,
                        type_str=current_type.strip(),
                        blocks=current_blocks
                    ))
                    item_index += 1
                current_type = child.get_text()
                current_blocks = []
            elif child.name:
                current_blocks.append(child)
            elif isinstance(child, str) and child.strip():
                current_blocks.append(child)
                
        # Append the final item of the entry
        if current_blocks:
            releases.append(create_release_item(
                entry_id=f"{entry_id}_{item_index}",
                date=title,
                raw_date=updated,
                link=link,
                type_str=current_type.strip(),
                blocks=current_blocks
            ))
            
    return releases

def get_releases_data(force_refresh=False):
    now = time.time()
    
    if force_refresh or not CACHE["data"] or (now - CACHE["last_fetched"] > CACHE_DURATION):
        try:
            CACHE["data"] = fetch_and_parse_releases()
            CACHE["last_fetched"] = now
            CACHE["status"] = "success"
            CACHE["warning_message"] = None
        except Exception as e:
            print(f"Error fetching release notes: {e}")
            if CACHE["data"]:
                CACHE["status"] = "warning"
                CACHE["warning_message"] = f"Failed to refresh data: {str(e)}. Showing cached data."
            else:
                return {
                    "status": "error",
                    "message": f"Failed to load release notes: {str(e)}"
                }, 500
                
    last_updated_str = datetime.fromtimestamp(CACHE["last_fetched"]).strftime("%Y-%m-%d %I:%M:%S %p")
    return {
        "status": CACHE["status"],
        "warning": CACHE["warning_message"],
        "last_updated": last_updated_str,
        "releases": CACHE["data"]
    }, 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/releases')
def api_releases():
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    data, code = get_releases_data(force_refresh)
    return jsonify(data), code

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
