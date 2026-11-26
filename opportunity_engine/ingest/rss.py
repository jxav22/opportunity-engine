"""RSS/Atom feed adapter (feedparser)."""

from __future__ import annotations

import hashlib
from email.utils import parsedate_to_datetime
from datetime import timezone

import feedparser

from opportunity_engine.ingest.base import IngestContext, RawItem, safe_get


def _entry_date(entry: dict) -> str | None:
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError, IndexError, OverflowError):
            # feedparser may already give structured time
            pass
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if not parsed:
            continue
        try:
            from time import mktime
            from datetime import datetime

            dt = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return None


class RssAdapter:
    name = "rss"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        feed_url = config.get("url") or config.get("feed_url")
        if not feed_url:
            raise ValueError("rss config requires url")
        company_name = config.get("company_name") or config.get("default_company")
        category = config.get("category") or "employment"
        max_items = int(config.get("max_items") or 100)
        resp = safe_get(ctx, feed_url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        feed_title = (parsed.feed.get("title") if parsed.feed else None) or company_name
        items: list[RawItem] = []
        for entry in (parsed.entries or [])[:max_items]:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            link = entry.get("link") or ""
            entry_id = entry.get("id") or entry.get("guid") or link or title
            external_id = f"rss:{hashlib.sha256(str(entry_id).encode()).hexdigest()[:24]}"
            description = entry.get("summary") or entry.get("description")
            # Remotive and similar often encode company in title "Role at Company"
            inferred_company = company_name or feed_title
            if config.get("infer_company_from_title") and " at " in title:
                parts = title.rsplit(" at ", 1)
                if len(parts) == 2 and parts[1].strip():
                    inferred_company = parts[1].strip()
                    title = parts[0].strip() or title
            items.append(
                RawItem(
                    external_id=external_id,
                    title=title,
                    url=link,
                    company_name=inferred_company,
                    location=config.get("default_location"),
                    description=description,
                    posted_at=_entry_date(entry),
                    category=category,
                    raw={
                        "id": entry.get("id"),
                        "title": entry.get("title"),
                        "link": link,
                        "summary": description,
                        "published": entry.get("published"),
                        "feed_url": feed_url,
                    },
                )
            )
        return items
