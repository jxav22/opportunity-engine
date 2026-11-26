"""Greenhouse public board API adapter."""

from __future__ import annotations

from opportunity_engine.ingest.base import IngestContext, RawItem, safe_get


class GreenhouseAdapter:
    name = "greenhouse"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        token = config.get("board_token") or config.get("token")
        if not token:
            raise ValueError("greenhouse config requires board_token")
        company_name = config.get("company_name") or token
        content = bool(config.get("content", False))
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        params = {"content": "true"} if content else None
        resp = safe_get(ctx, url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        jobs = payload.get("jobs") or []
        items: list[RawItem] = []
        for job in jobs:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            title = (job.get("title") or "").strip()
            if not title:
                continue
            abs_url = job.get("absolute_url") or ""
            loc = job.get("location") or {}
            location = loc.get("name") if isinstance(loc, dict) else None
            description = job.get("content")
            posted_at = job.get("first_published") or job.get("updated_at")
            company = (job.get("company_name") or company_name or "").strip() or company_name
            items.append(
                RawItem(
                    external_id=f"greenhouse:{token}:{job_id}",
                    title=title,
                    url=abs_url,
                    company_name=company,
                    location=location,
                    description=description,
                    posted_at=posted_at,
                    category="employment",
                    raw=job if isinstance(job, dict) else {"value": job},
                )
            )
        return items
