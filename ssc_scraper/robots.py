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
    def _parser_for(self, scheme_host: str) -> RobotFileParser | None:
        if scheme_host in self._cache:
            return self._cache[scheme_host]

        parser = RobotFileParser()
        robots_url = f"{scheme_host}/robots.txt"
        try:
            response = requests.get(
                robots_url,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
            if response.status_code == 200 and response.text:
                parser.parse(response.text.splitlines())
                log.debug("Loaded robots.txt for %s", scheme_host)
                self._cache[scheme_host] = parser
            else:
                log.debug(
                    "No robots.txt at %s (HTTP %s) - no directives apply",
                    robots_url,
                    response.status_code,
                )
                self._cache[scheme_host] = None
        except requests.RequestException as exc:  # network/anti-bot failure
            log.warning(
                "Could not fetch robots.txt for %s: %s - treating host as "
                "allowed by convention; verify manually before heavy crawling",
                scheme_host,
                exc,
            )
            self._cache[scheme_host] = None
        return self._cache[scheme_host]

    # ------------------------------------------------------------------
    def is_allowed(self, url: str) -> tuple[bool, str]:
        """Return (allowed, reason) for *url*. Never raises."""
        if not self.respect:
            log.warning("robots.txt checking is DISABLED by config - not recommended")
            return True, "robots checking disabled by config"

        parts = urlparse(url)
        if not parts.netloc:
            return False, "invalid URL"
        scheme_host = f"{parts.scheme}://{parts.netloc}"
        parser = self._parser_for(scheme_host)
        if parser is None:
            return True, "no robots.txt found"
        if parser.can_fetch(self.user_agent, url):
            return True, "allowed by robots.txt"
        return False, "disallowed by robots.txt"
