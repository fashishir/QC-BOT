"""Polite, checkpointed BFS crawler for source discovery.

Discovers document links (PDF/DOC/images) from seed pages and records them
as download candidates in the crawl_state table so runs are resumable.
All requests go through PoliteHttpClient (robots.txt + rate limiting).
Crawling stays strictly inside the source's allow-domains and any optional
keyword filter; nothing is ever fetched from hosts the config does not list.
"""

from __future__ import annotations

from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .config import Settings, SourceConfig
from .http_client import PoliteHttpClient
from .logging_setup import get_logger

log = get_logger("crawler")

_SKIP_PREFIXES = ("mailto:", "javascript:", "tel:", "data:", "#")


class Crawler:
    """Breadth-first page crawler, bounded and checkpointed per source."""

    def __init__(self, db, client: PoliteHttpClient, settings: Settings):
        self.db = db
        self.client = client
        self.settings = settings

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _normalize_url(base_url: str, href: str) -> str | None:
        if not href:
            return None
        href = href.strip()
        if href.startswith(_SKIP_PREFIXES):
            return None
        absolute = urljoin(base_url, href)
        parts = urlparse(absolute)
        if parts.scheme not in ("http", "https"):
            return None
        # drop fragments, keep path + query
        return urlunparse((parts.scheme, parts.netloc, parts.path, "", parts.query, ""))

    @staticmethod
    def _host_allowed(url: str, allow_domains: list[str]) -> bool:
        allowed = {d.lower() for d in allow_domains if d}
        return urlparse(url).netloc.lower() in allowed

    @staticmethod
    def _passes_keyword_filter(url: str, keywords: list[str]) -> bool:
        if not keywords:
            return True
        lowered = url.lower()
        return any(str(k).lower() in lowered for k in keywords)

    @staticmethod
    def _extension(url: str) -> str:
        path = urlparse(url).path.lower()
        dot = path.rfind(".")
        return path[dot:] if dot != -1 else ""

    # ---------------------------------------------------------------- main
    def crawl_source(self, source: SourceConfig) -> dict:
        """Crawl one source within its allow-domains; returns run statistics."""
        stats = {"pages_visited": 0, "documents_found": 0, "failed": 0, "skipped": 0}
        pending: deque[tuple[str, int]] = deque()

        for seed in source.seed_urls:
            state = self.db.get_crawl_state(seed)
            if state is None or state["status"] == "failed":
                self.db.set_crawl_state(seed, source.name, "pending", 0)
                pending.append((seed, 0))
            else:
                log.debug("Seed already %s: %s (resume)", state["status"], seed)

        document_extensions = {e.lower() for e in self.settings.allowed_extensions}
        html_extensions = {".html", ".htm"}
        pages_cap = self.settings.max_pages_per_source

        while pending and stats["pages_visited"] < pages_cap:
            url, depth = pending.popleft()
            state = self.db.get_crawl_state(url)
            if state and state["status"] in ("visited", "skipped"):
                continue

            result = self.client.fetch(url)
            if result.blocked:
                # Never bypass: flag source for manual review and move on.
                self.db.set_crawl_state(url, source.name, "skipped", depth, error=result.error)
                self.db.set_source_status(
                    source.name, "manual_review",
                    note=f"HTTP {result.status_code} (access-restricted) at {url}",
                )
                stats["failed"] += 1
                continue
            if not result.ok:
                self.db.set_crawl_state(
                    url, source.name, "failed", depth,
                    error=result.error or f"HTTP {result.status_code}",
                )
                stats["failed"] += 1
                continue
            if not result.text or not result.text.lstrip().startswith("<"):
                self.db.set_crawl_state(url, source.name, "visited", depth)
                stats["pages_visited"] += 1
                continue  # not an HTML page

            page_title, docs, pages = self._parse_links(
                url, result.text, source, document_extensions, html_extensions
            )
            for doc_url, (anchor, found_on) in docs.items():
                self.db.set_crawl_state(
                    doc_url, source.name, "candidate", depth + 1,
                    found_on=found_on, context=anchor,
                )
                stats["documents_found"] += 1
            for page_url in pages:
                if self.db.get_crawl_state(page_url) is None:
                    self.db.set_crawl_state(
                        page_url, source.name, "pending", depth + 1, found_on=url,
                    )
                    pending.append((page_url, depth + 1))

            self.db.set_crawl_state(url, source.name, "visited", depth, context=page_title)
            stats["pages_visited"] += 1

        if stats["pages_visited"] >= pages_cap:
            log.warning(
                "Source %r hit max_pages_per_source=%d; re-run later to continue",
                source.name, pages_cap,
            )
        log.info(
            "Crawl finished for %r: visited=%d, documents=%d, failed=%d",
            source.name, stats["pages_visited"], stats["documents_found"], stats["failed"],
        )
        return stats

    # -------------------------------------------------------------- parsing
    def _parse_links(self, page_url: str, html: str, source: SourceConfig,
                     document_extensions: set[str], html_extensions: set[str]):
        """Return (title, {doc_url: (anchor_text, page_url)}, [page_urls])."""
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:  # pragma: no cover - lxml ships in requirements
            soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.get_text(strip=True) if soup.title else "")[:300]

        documents: dict[str, tuple[str, str]] = {}
        page_links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            target = self._normalize_url(page_url, anchor.get("href"))
            if not target:
                continue
            anchor_text = anchor.get_text(strip=True)[:300]
            extension = self._extension(target)
            if extension in document_extensions:
                if target not in documents:
                    documents[target] = (anchor_text, page_url)
            elif self.settings.download_html_pages and extension in html_extensions:
                if target not in documents:
                    documents[target] = (anchor_text, page_url)
            elif self._host_allowed(target, source.allow_domains) and \
                    self._passes_keyword_filter(target, source.keywords):
                page_links.append(target)
            else:
                log.debug("Skipping off-scope link: %s", target)
        return title, documents, page_links
