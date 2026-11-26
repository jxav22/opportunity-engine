"""Manual JSON / file registration adapter — never fabricates jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opportunity_engine.ingest.base import IngestContext, RawItem


def _load_items(config: dict) -> list[dict[str, Any]]:
    if "items" in config and isinstance(config["items"], list):
        return list(config["items"])
    path = config.get("path") or config.get("file")
    if not path:
        raise ValueError("manual config requires items[] or path")
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"manual items file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    if not isinstance(data, list):
        raise ValueError("manual file must be a list or {items: [...]}")
    return data


class ManualAdapter:
    name = "manual"

    def fetch(self, config: dict, ctx: IngestContext) -> list[RawItem]:
        # ctx unused — no network; keep signature for protocol
        _ = ctx
        raw_items = _load_items(config)
        items: list[RawItem] = []
        for i, row in enumerate(raw_items):
            if not isinstance(row, dict):
                continue
            title = (row.get("title") or "").strip()
            url = (row.get("url") or "").strip()
            if not title or not url:
                continue
            external_id = str(row.get("external_id") or row.get("id") or f"manual:{i}:{title}")
            items.append(
                RawItem(
                    external_id=f"manual:{external_id}",
                    title=title,
                    url=url,
                    company_name=(row.get("company_name") or row.get("company") or "Unknown").strip(),
                    location=row.get("location"),
                    description=row.get("description"),
                    posted_at=row.get("posted_at"),
                    category=row.get("category") or "employment",
                    raw=row,
                )
            )
        return items
