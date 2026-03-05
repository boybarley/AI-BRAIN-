"""
crawl.py — Website crawler for AI Brain knowledge base
Usage:
    python crawl.py https://example.com
    python crawl.py https://example.com --depth 3 --max-pages 100
"""

import os
import re
import logging
import argparse
from urllib.parse import urljoin, urlparse
from collections import deque

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".zip", ".tar", ".gz", ".css", ".js", ".ico", ".woff", ".woff2",
)


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", text)


def get_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("title") or soup.find("h1")
    return tag.get_text().strip() if tag else "untitled"


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text)[:80].strip("-")


def crawl(start_url: str, max_depth: int = 2, max_pages: int = 50):
    base_domain = urlparse(start_url).netloc
    visited = set()
    queue = deque([(start_url, 0)])
    saved = 0

    os.makedirs(DATA_DIR, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; AIBrainBot/1.0)"

    logger.info(f"Crawling: {start_url}")
    logger.info(f"  Domain: {base_domain} | Depth: {max_depth} | Max: {max_pages}")
    print()

    while queue and saved < max_pages:
        url, depth = queue.popleft()
        url = url.split("#")[0].rstrip("/")

        if url in visited:
            continue
        visited.add(url)

        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"  [{resp.status_code}] {url}")
                continue

            if "text/html" not in resp.headers.get("content-type", ""):
                continue

            html = resp.text
            title = get_title(html)
            text = clean_text(html)

            if len(text.strip()) < 100:
                logger.info(f"  SKIP (short): {url}")
                continue

            # Save
            slug = slugify(title) or f"page-{saved}"
            filename = f"crawl_{slug}.txt"
            filepath = os.path.join(DATA_DIR, filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"crawl_{slug}_{counter}.txt"
                filepath = os.path.join(DATA_DIR, filename)
                counter += 1

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\nTitle: {title}\n{'=' * 60}\n\n{text}")

            saved += 1
            logger.info(f"  ✓ [{saved}/{max_pages}] {url} → {filename}")

            # Extract links
            if depth < max_depth:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    full = urljoin(url, a["href"])
                    parsed = urlparse(full)
                    if (
                        parsed.netloc == base_domain
                        and full not in visited
                        and not any(parsed.path.lower().endswith(e) for e in SKIP_EXTENSIONS)
                    ):
                        queue.append((full, depth + 1))

        except requests.RequestException as e:
            logger.warning(f"  FAIL: {url} — {e}")
        except Exception as e:
            logger.error(f"  ERROR: {url} — {e}")

    print()
    logger.info(f"Done! {saved} pages saved to {DATA_DIR}/")
    logger.info(f"Next: python ingest_data.py")


def main():
    parser = argparse.ArgumentParser(description="Crawl website for AI Brain")
    parser.add_argument("url", help="Starting URL")
    parser.add_argument("--depth", type=int, default=2, help="Max depth (default: 2)")
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages (default: 50)")
    args = parser.parse_args()
    crawl(args.url, args.depth, args.max_pages)


if __name__ == "__main__":
    main()
