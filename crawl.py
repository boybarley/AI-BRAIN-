"""
crawl.py — Smart Web Crawler
==============================
Crawler cerdas untuk mengisi knowledge base RAG.

Fitur:
  - Antrian URL untuk crawling multi-halaman
  - Ekstraksi teks bersih (hapus nav, footer, script, style)
  - Metadata source URL tersimpan di setiap dokumen
  - Deteksi duplikat: skip URL yang sudah ada di FAISS
  - Pembatasan domain (same-domain only)
  - Rate limiting (delay antar request)
  - Merge dengan index FAISS yang sudah ada

Usage:
  python crawl.py https://example.com --max-pages 20 --delay 1.5
  python crawl.py https://site1.com https://site2.com/page
"""

import os
import sys
import time
import logging
from typing import List, Set
from urllib.parse import urljoin, urlparse
from collections import deque

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from core_rag import load_config, create_embeddings

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class SmartCrawler:
    """
    Web crawler dengan kemampuan:
    - BFS crawling dari seed URLs
    - Skip URL yang sudah terindeks
    - Merge hasil ke FAISS index yang ada
    """

    def __init__(self, config: dict = None):
        self.config = config or load_config()
        self.visited_urls: Set[str] = set()
        self.existing_sources: Set[str] = set()
        self.documents: List[Document] = []

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; AI-Brain-Crawler/1.0; "
                "+https://github.com/ai-brain)"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        })

        self._load_existing_sources()

    def _load_existing_sources(self):
        """Load sumber yang sudah ada di FAISS untuk menghindari duplikat."""
        try:
            vs_path = self.config.get("vector_store_path", "db/faiss_index")
            full_path = os.path.join(BASE_DIR, vs_path)

            if not os.path.exists(full_path):
                return

            embeddings = create_embeddings(self.config)
            store = FAISS.load_local(
                full_path, embeddings,
                allow_dangerous_deserialization=True,
            )

            # Extract all unique sources from docstore
            for doc_id in store.docstore._dict:
                doc = store.docstore._dict[doc_id]
                source = doc.metadata.get("source", "")
                if source:
                    self.existing_sources.add(source)

            logger.info(
                f"📋 Found {len(self.existing_sources)} existing sources "
                f"in FAISS index"
            )

        except Exception as e:
            logger.warning(f"Could not load existing sources: {e}")

    def _normalize_url(self, url: str) -> str:
        """Normalize URL: remove fragment, trailing slash."""
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    def _clean_text(self, soup: BeautifulSoup) -> str:
        """Ekstrak clean text dari HTML, hapus elemen non-konten."""
        # Remove non-content elements
        for tag in soup(
            ["script", "style", "nav", "footer", "header",
             "aside", "noscript", "iframe", "form"]
        ):
            tag.decompose()

        # Get text with newline separators
        text = soup.get_text(separator="\n", strip=True)

        # Clean up: remove excessive blank lines
        lines = [line.strip() for line in text.splitlines()]
        cleaned = "\n".join(line for line in lines if line)

        return cleaned

    def _extract_links(
        self, soup: BeautifulSoup, base_url: str, same_domain: bool
    ) -> List[str]:
        """Extract and normalize links from page."""
        links = []
        base_domain = urlparse(base_url).netloc

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]

            # Skip non-http links
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            full_url = urljoin(base_url, href)
            normalized = self._normalize_url(full_url)
            parsed = urlparse(normalized)

            # Domain filter
            if same_domain and parsed.netloc != base_domain:
                continue

            # Scheme filter
            if parsed.scheme not in ("http", "https"):
                continue

            # Skip common non-content paths
            skip_exts = (
                ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
                ".css", ".js", ".ico", ".woff", ".woff2", ".ttf",
                ".zip", ".tar", ".gz", ".mp4", ".mp3",
            )
            if any(parsed.path.lower().endswith(ext) for ext in skip_exts):
                continue

            if normalized not in self.visited_urls:
                links.append(normalized)

        return links

    def crawl(
        self,
        start_urls: List[str],
        max_pages: int = 50,
        same_domain: bool = True,
        delay: float = 1.0,
    ):
        """
        Crawl halaman web secara BFS dari seed URLs.
        
        Args:
            start_urls:   List URL untuk memulai crawling
            max_pages:    Maksimum halaman yang dicrawl
            same_domain:  Hanya ikuti link di domain yang sama
            delay:        Jeda antar request (detik)
        """
        queue = deque()
        for url in start_urls:
            queue.append(self._normalize_url(url))

        pages_crawled = 0

        logger.info(
            f"🕷️  Starting crawl: {len(start_urls)} seed URL(s), "
            f"max_pages={max_pages}, delay={delay}s"
        )

        while queue and pages_crawled < max_pages:
            url = queue.popleft()

            if url in self.visited_urls:
                continue

            if url in self.existing_sources:
                logger.info(f"⏭️  Skip (already indexed): {url}")
                self.visited_urls.add(url)
                continue

            self.visited_urls.add(url)

            try:
                logger.info(
                    f"🔍 [{pages_crawled + 1}/{max_pages}] Crawling: {url}"
                )

                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()

                # Only process HTML
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    logger.debug(f"Skip non-HTML: {content_type}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                text = self._clean_text(soup)

                if len(text) < 50:
                    logger.warning(
                        f"⚠️  Skip (too little content, "
                        f"{len(text)} chars): {url}"
                    )
                    continue

                # Extract title
                title = ""
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()

                # Create LangChain Document with source metadata
                doc = Document(
                    page_content=text,
                    metadata={
                        "source": url,
                        "title": title,
                        "type": "web",
                    },
                )
                self.documents.append(doc)
                pages_crawled += 1

                # Extract links for further crawling
                new_links = self._extract_links(soup, url, same_domain)
                for link in new_links:
                    if link not in self.visited_urls:
                        queue.append(link)

                time.sleep(delay)

            except requests.Timeout:
                logger.warning(f"⏱️  Timeout: {url}")
            except requests.HTTPError as e:
                logger.warning(f"🚫 HTTP {e.response.status_code}: {url}")
            except requests.RequestException as e:
                logger.error(f"❌ Request failed: {url} — {e}")

        logger.info(
            f"\n{'='*50}\n"
            f"✅ Crawling complete!\n"
            f"   Pages crawled: {pages_crawled}\n"
            f"   Documents collected: {len(self.documents)}\n"
            f"   URLs visited: {len(self.visited_urls)}\n"
            f"{'='*50}"
        )

    def save_to_faiss(self):
        """Split dokumen dan simpan/merge ke FAISS index."""
        if not self.documents:
            logger.warning("No documents to save")
            return

        # Text splitting
        chunk_size = self.config.get("chunk_size", 1000)
        chunk_overlap = self.config.get("chunk_overlap", 200)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        chunks = splitter.split_documents(self.documents)
        logger.info(
            f"✂️  Split {len(self.documents)} documents → "
            f"{len(chunks)} chunks "
            f"(size={chunk_size}, overlap={chunk_overlap})"
        )

        # Create embeddings
        embeddings = create_embeddings(self.config)

        # Check for existing index
        vs_path = self.config.get("vector_store_path", "db/faiss_index")
        full_path = os.path.join(BASE_DIR, vs_path)

        if os.path.exists(full_path):
            logger.info("🔄 Merging with existing FAISS index...")
            existing = FAISS.load_local(
                full_path, embeddings,
                allow_dangerous_deserialization=True,
            )
            new_store = FAISS.from_documents(chunks, embeddings)
            existing.merge_from(new_store)
            existing.save_local(full_path)
            logger.info(
                f"💾 Merged! Total vectors: {existing.index.ntotal}"
            )
        else:
            logger.info("🆕 Creating new FAISS index...")
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            store = FAISS.from_documents(chunks, embeddings)
            store.save_local(full_path)
            logger.info(
                f"💾 Created! Total vectors: {store.index.ntotal}"
            )

        logger.info(f"📍 Index saved to: {full_path}")


# ══════════════════════════════════════════════════════════════
#  CLI INTERFACE
# ══════════════════════════════════════════════════════════════

def main():
    """Command-line interface for the crawler."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart Web Crawler for AI Brain RAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python crawl.py https://example.com
  python crawl.py https://docs.example.com --max-pages 30 --delay 2
  python crawl.py https://site1.com https://site2.com/page
  python crawl.py https://external.com --no-same-domain --max-pages 5
        """,
    )
    parser.add_argument(
        "urls", nargs="+", help="Seed URL(s) to start crawling"
    )
    parser.add_argument(
        "--max-pages", type=int, default=50,
        help="Maximum pages to crawl (default: 50)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Delay between requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--no-same-domain", action="store_true",
        help="Allow crawling across different domains",
    )

    args = parser.parse_args()

    crawler = SmartCrawler()
    crawler.crawl(
        start_urls=args.urls,
        max_pages=args.max_pages,
        same_domain=not args.no_same_domain,
        delay=args.delay,
    )
    crawler.save_to_faiss()


if __name__ == "__main__":
    main()
