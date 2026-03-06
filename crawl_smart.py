"""
crawl_smart.py — Smart crawler that extracts items WITH share links
Specifically designed for membersbwk.baliwithkidz.com
"""

import os
import re
import logging
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BASE_URL = "https://membersbwk.baliwithkidz.com"

# Pages to crawl
PAGES = {
    "activities": f"{BASE_URL}/activities.php",
    "nanny":      f"{BASE_URL}/nanny.php",
    "driver":     f"{BASE_URL}/car.php",
}

# IDs to skip (not actual items)
SKIP_IDS = {
    "mainContainer", "cardContainer", "viewAllBtnContainer",
    "iosSearchContainer", "iosSearchResults", "iosSearchInput",
    "showmembercard", "checkMembershipModalLabel", "memberPromo",
    "text",  # section headers
}

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (compatible; BWKBot/2.0)"


def extract_items(page_name, page_url):
    """Extract all items from a listing page."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Crawling: {page_name} → {page_url}")
    
    resp = session.get(page_url, timeout=30)
    if resp.status_code != 200:
        logger.error(f"  HTTP {resp.status_code}")
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    
    # Find all card-item divs
    cards = soup.find_all("div", class_="card-item")
    logger.info(f"  Found {len(cards)} card items")
    
    for card in cards:
        item_id = card.get("id", "")
        if not item_id or item_id in SKIP_IDS:
            continue
        
        # Build share URL
        share_url = f"{page_url}?view={item_id}"
        
        # Extract title
        title_tag = card.find("h3", class_="card-title")
        title = title_tag.get_text(strip=True) if title_tag else item_id
        
        # Extract subtitle (text-muted)
        subtitle_tag = card.find("p", class_="text-muted")
        subtitle = subtitle_tag.get_text(strip=True) if subtitle_tag else ""
        
        # Extract description (all card-text that are NOT text-muted)
        descriptions = []
        for p in card.find_all("p", class_="card-text"):
            if "text-muted" not in p.get("class", []):
                text = p.get_text(strip=True)
                if text and text != subtitle:
                    descriptions.append(text)
        description = "\n".join(descriptions)
        
        # Extract clamp-text (some pages use this)
        clamp = card.find("div", class_="clamp-text")
        if clamp and not description:
            description = clamp.get_text(strip=True)
        
        # Extract WhatsApp link
        wa_link = ""
        wa_tag = card.find("a", href=re.compile(r"wa\.me"))
        if wa_tag:
            wa_link = wa_tag["href"]
        
        # Extract Phone
        phone = ""
        phone_tag = card.find("a", href=re.compile(r"^tel:"))
        if phone_tag:
            phone = phone_tag["href"].replace("tel:", "")
        
        # Extract Messenger
        messenger = ""
        msg_tag = card.find("a", href=re.compile(r"m\.me"))
        if msg_tag:
            messenger = msg_tag["href"]
        
        # Extract data-keywords
        keywords = card.get("data-keywords", "")
        
        # Also try to get OG data from individual page
        og_description = get_og_description(share_url)
        if og_description and len(og_description) > len(description):
            description = og_description
        
        item = {
            "id": item_id,
            "title": title,
            "subtitle": subtitle,
            "description": description,
            "category": page_name,
            "url": share_url,
            "whatsapp": wa_link,
            "phone": phone,
            "messenger": messenger,
            "keywords": keywords,
        }
        items.append(item)
        logger.info(f"  ✓ {title} → {share_url}")
    
    return items


def get_og_description(url):
    """Get OG description from individual item page."""
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:description")
        return og["content"].strip() if og else ""
    except Exception:
        return ""


def save_items(items, page_name):
    """Save items as structured text files for RAG ingestion."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Save individual items
    for item in items:
        filename = f"bwk_{page_name}_{item['id']}.txt"
        filepath = os.path.join(DATA_DIR, filename)
        
        content = f"""## {item['title']}
Kategori: {item['category'].title()}
URL: {item['url']}
"""
        if item['subtitle']:
            content += f"Tagline: {item['subtitle']}\n"
        
        if item['description']:
            content += f"\nDeskripsi:\n{item['description']}\n"
        
        if item['keywords']:
            content += f"\nKeywords: {item['keywords']}\n"
        
        content += "\nKontak:\n"
        if item['whatsapp']:
            content += f"  WhatsApp: {item['whatsapp']}\n"
        if item['phone']:
            content += f"  Phone: {item['phone']}\n"
        if item['messenger']:
            content += f"  Messenger: {item['messenger']}\n"
        
        content += f"\nLink detail: {item['url']}\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    
    # Also save a summary file per category
    summary_file = os.path.join(DATA_DIR, f"bwk_{page_name}_summary.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"# Daftar {page_name.title()} - Baliwithkidz\n\n")
        for item in items:
            f.write(f"- **{item['title']}**: {item['subtitle']}\n")
            f.write(f"  Link: {item['url']}\n")
            if item['whatsapp']:
                f.write(f"  WhatsApp: {item['whatsapp']}\n")
            f.write("\n")
    
    logger.info(f"  Saved {len(items)} items + 1 summary → data/bwk_{page_name}_*.txt")


def main():
    all_items = []
    
    for page_name, page_url in PAGES.items():
        items = extract_items(page_name, page_url)
        save_items(items, page_name)
        all_items.extend(items)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"CRAWL COMPLETE: {len(all_items)} items total")
    print(f"{'='*60}")
    for page_name in PAGES:
        count = len([i for i in all_items if i['category'] == page_name])
        print(f"  {page_name}: {count} items")
    print(f"\nFiles saved to: {DATA_DIR}/")
    print(f"Next: python ingest_data.py")


if __name__ == "__main__":
    main()
