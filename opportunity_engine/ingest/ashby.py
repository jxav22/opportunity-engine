"""Ashby public job board API adapter."""

from __future__ import annotations

from opportunity_engine.ingest.base import IngestContext, RawItem, safe_get


class AshbyAdapter:
    name = "ashby"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        board = config.get("board") or config.get("organization") or config.get("slug")
        if not board:
            raise ValueError("ashby config requires board")
        company_name = config.get("company_name") or board
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
        resp = safe_get(ctx, url)
        resp.raise_for_status()
        payload = resp.json()
        jobs = payload.get("jobs") or []
        items: list[RawItem] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            if job.get("isListed") is False:
                continue
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            title = (job.get("title") or "").strip()
            if not title:
                continue
            def _loc_str(loc: object) -> str:
                if loc is None:
                    return ""
                if isinstance(loc, str):
                    return loc
                if isinstance(loc, dict):
                    return str(
                        loc.get("name")
                        or loc.get("location")
                        or loc.get("address")
                        or loc.get("postalAddress")
                        or ""
                    )
                return str(loc)

            location = _loc_str(job.get("location")) or None
            secondary = job.get("secondaryLocations") or []
            if location and secondary:
                extra = [_loc_str(loc) for loc in secondary]
                extra = [e for e in extra if e]
                if extra:
                    location = f"{location}; " + "; ".join(extra)
            description = job.get("descriptionPlain") or job.get("descriptionHtml")
            items.append(
                RawItem(
                    external_id=f"ashby:{board}:{job_id}",
                    title=title,
                    url=job.get("jobUrl") or job.get("applyUrl") or "",
                    company_name=company_name,
                    location=location if isinstance(location, str) else None,
                    description=description,
                    posted_at=job.get("publishedAt"),
                    category="employment",
                    raw=job,
                )
            )
        return items
