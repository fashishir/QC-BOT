"""robots.txt compliance gate.

Every URL - crawl pages and file downloads alike - must pass through this
gate before any HTTP request is made. robots.txt is fetched once per host
and cached. If robots.txt itself cannot be retrieved (network error), we
log a warning and conservatively treat the host as allowed *only because*
the standard convention is that an unreachable robots.txt imposes no
directive; the event is always logged for manual review.
"""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from .logging_setup import get_logger

log = get_logger("robots")


class RobotsGate:
    """Caching robots.txt checker for a single user-agent."""

    def __init__(self, user_agent: str, timeout: int = 15, respect_robots: bool = True):
        self.user_agent = user_agent
        self.timeout = timeout
        self.respect = respect_robots
        self._cache: dict[str, RobotFileParser | None] = {}

    # ------------------------------------------------------------------
    def _load(self, host_url: str) -> RobotFileParser | None:
        if host_url in self._cache:
            return self._cache[host_url]
        parser: RobotFileParser | None = None
        try:
            response = requests.get(
                host_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            if response.status_code == 200:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
            else:
                log.warning(
                    "robots.txt for %s returned HTTP %s - treating host as allowed",
                    host_url,
                    response.status_code,
                )
        except requests.RequestException as exc:
            log.warning(
                "robots.txt for %s could not be fetched (%s) - treating host as allowed",
                host_url,
                exc,
            )
        self._cache[host_url] = parser
        return parser

    # ------------------------------------------------------------------
    def is_allowed(self, url: str) -> tuple[bool, str]:
        """Return (allowed, reason) for *url*."""
        if not self.respect:
            return True, "robots checks disabled by configuration"
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "invalid URL"
        if parsed.scheme not in ("http", "https"):
            return False, f"unsupported scheme {parsed.scheme!r}"
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._load(robots_url)
        if parser is None:
            return True, "robots.txt unavailable; allowed by convention"
        if parser.can_fetch(self.user_agent, url):
            return True, "allowed by robots.txt"
        return False, "disallowed by robots.txt"
