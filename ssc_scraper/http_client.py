"""Polite HTTP client.

Ethics are enforced HERE, not by convention:
  * robots.txt gate before every request (see RobotsGate)
  * per-host rate limiting (minimum delay between requests)
  * exponential-backoff retries for transient failures only
  * 401/403/anti-bot responses are NEVER retried or bypassed - the source
    is flagged for manual review instead
  * identifying User-Agent with contact information
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

from .config import Settings
from .logging_setup import get_logger
from .robots import RobotsGate

log = get_logger("http")

# Authentication / protection walls: never retry, never bypass.
BLOCKED_STATUS_CODES = {401, 403}


class BlockedError(RuntimeError):
    """The server denied us (auth wall, paywall, anti-bot). Manual review needed."""

    def __init__(self, url: str, status_code: int):
        super().__init__(
            f"HTTP {status_code} for {url} - access-restricted; marked for manual "
            f"review. This bot does not bypass authentication or protection."
        )
        self.url = url
        self.status_code = status_code


class FetchError(RuntimeError):
    """All retries exhausted or unrecoverable transport failure."""


@dataclass
class FetchResult:
    ok: bool
    url: str
    status_code: int = 0
    content: bytes = b""
    text: str = ""
    error: str | None = None
    blocked: bool = False


class PoliteHttpClient:
    """Single-threaded, rate-limited, robots-aware HTTP fetcher."""

    def __init__(self, settings: Settings, robots: RobotsGate | None = None):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept-Language": "bn, en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/pdf,image/*;q=0.8,*/*;q=0.5",
            }
        )
        self.robots = robots or RobotsGate(
            settings.user_agent,
            settings.request_timeout_seconds,
            settings.respect_robots_txt,
        )
        self._last_request_at: dict[str, float] = {}
        self.blocked_hosts: set[str] = set()      # hosts that returned 401/403
        self.robots_blocked_hosts: set[str] = set()

    # ------------------------------------------------------------------
    def _wait_turn(self, url: str) -> None:
        """Enforce the per-host politeness delay."""
        host = urlparse(url).netloc
        last = self._last_request_at.get(host)
        if last is not None:
            remaining = self.settings.request_delay_seconds - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at[host] = time.monotonic()

    def _check_robots(self, url: str) -> None:
        allowed, reason = self.robots.is_allowed(url)
        if not allowed:
            self.robots_blocked_hosts.add(urlparse(url).netloc)
            log.info("ROBOTS-DISALLOWED %s (%s) - skipping", url, reason)
            raise FetchError(f"robots.txt disallows: {url} ({reason})")

    # ------------------------------------------------------------------
    def fetch(self, url: str) -> FetchResult:
        """GET *url* into memory (HTML pages)."""
        try:
            response = self._get_with_retries(url, stream=False)
        except BlockedError as exc:
            return FetchResult(ok=False, url=url, status_code=exc.status_code, blocked=True, error=str(exc))
        except FetchError as exc:
            return FetchResult(ok=False, url=url, error=str(exc))
        return FetchResult(
            ok=response.status_code < 400,
            url=response.url,
            status_code=response.status_code,
            content=response.content,
            text=response.text,
        )

    def fetch_stream(self, url: str) -> requests.Response:
        """GET *url* with stream=True for large file downloads.

        Raises BlockedError / FetchError. Caller must consume and close.
        """
        return self._get_with_retries(url, stream=True)

    # ------------------------------------------------------------------
    def _get_with_retries(self, url: str, *, stream: bool) -> requests.Response:
        self._check_robots(url)
        last_error: Exception | None = None

        for attempt in range(1, self.settings.max_retries + 1):
            self._wait_turn(url)
            try:
                response = self.session.get(
                    url,
                    timeout=self.settings.request_timeout_seconds,
                    stream=stream,
                )

                if response.status_code in BLOCKED_STATUS_CODES:
                    host = urlparse(response.url).netloc
                    self.blocked_hosts.add(host)
                    log.warning(
                        "BLOCKED %s -> HTTP %s. NOT bypassing; host flagged for manual review.",
                        url,
                        response.status_code,
                    )
                    raise BlockedError(url, response.status_code)

                if response.status_code == 429:  # rate limited by server
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if (retry_after or "").isdigit() else \
                        self.settings.backoff_factor ** attempt * 2
                    log.warning("HTTP 429 (rate limited) for %s - waiting %.1fs (server politely asked)", url, wait)
                    time.sleep(wait)
                    last_error = FetchError("HTTP 429")
                    continue

                if response.status_code >= 500:
                    last_error = FetchError(f"HTTP {response.status_code}")
                    log.warning("Server error HTTP %s for %s (attempt %d/%d)",
                                response.status_code, url, attempt, self.settings.max_retries)
                else:
                    return response

            except requests.RequestException as exc:
                last_error = exc
                log.warning("Request failed for %s (attempt %d/%d): %s", url, attempt, self.settings.max_retries, exc)

            wait = self.settings.backoff_factor ** attempt
            log.debug("Backing off %.1fs before retry", wait)
            time.sleep(wait)

        raise FetchError(f"Max retries ({self.settings.max_retries}) exceeded for {url}: {last_error}")

    def close(self) -> None:
        self.session.close()
