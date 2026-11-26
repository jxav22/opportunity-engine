"""Lever public postings API adapter."""

from __future__ import annotations

from datetime import datetime, timezone

from opportunity_engine.ingest.base import IngestContext, RawItem, safe_get


def _ms_to_iso(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    try:
        return (
            datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (ValueError, OSError, OverflowError):
        return None


class LeverAdapter:
    name = "lever"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        site = config.get("site") or config.get("company")
        if not site:
            raise ValueError("lever config requires site")
        company_name = config.get("company_name") or site
        url = f"https://api.lever.co/v0/postings/{site}"
        resp = safe_get(ctx, url, params={"mode": "json"})
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Lever response for {site}: {type(payload)}")
        items: list[RawItem] = []
        for job in payload:
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            title = (job.get("text") or "").strip()
            if not title:
                continue
            categories = job.get("categories") or {}
            location = None
            if isinstance(categories, dict):
                location = categories.get("location")
                if not location and categories.get("allLocations"):
                    locs = categories["allLocations"]
                    if isinstance(locs, list) and locs:
                        location = ", ".join(str(x) for x in locs)
            description = job.get("descriptionPlain") or job.get("description")
            posted_at = _ms_to_iso(job.get("createdAt"))
            items.append(
                RawItem(
                    external_id=f"lever:{site}:{job_id}",
                    title=title,
                    url=job.get("hostedUrl") or job.get("applyUrl") or "",
                    company_name=company_name,
                    location=location,
                    description=description,
                    posted_at=posted_at,
                    category="employment",
                    raw=job,
                )
            )
        return items
