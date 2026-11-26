"""GitHub Releases Atom/RSS adapter (optional; uses RSS fetch path)."""

from __future__ import annotations

from opportunity_engine.ingest.base import IngestContext, RawItem
from opportunity_engine.ingest.rss import RssAdapter


class GithubReleasesAdapter:
    """Fetch public GitHub release Atom feeds as community/engineering signals."""

    name = "github"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        owner = config.get("owner")
        repo = config.get("repo")
        if owner and repo:
            feed_url = f"https://github.com/{owner}/{repo}/releases.atom"
        else:
            feed_url = config.get("url") or config.get("feed_url")
        if not feed_url:
            raise ValueError("github adapter requires owner+repo or url")
        rss_config = {
            "url": feed_url,
            "company_name": config.get("company_name") or (f"{owner}/{repo}" if owner and repo else None),
            "category": config.get("category") or "community",
            "max_items": config.get("max_items") or 30,
            "default_location": config.get("default_location"),
        }
        return RssAdapter().fetch(rss_config, ctx)
