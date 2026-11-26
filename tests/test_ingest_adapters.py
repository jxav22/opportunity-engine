"""Adapter unit tests with fixtures (no network required for manual/normalize)."""

from __future__ import annotations

import json
from pathlib import Path

from opportunity_engine.ingest.base import IngestContext, RawItem
from opportunity_engine.ingest.manual import ManualAdapter
from opportunity_engine.ingest.pipeline import make_dedupe_key, normalize_raw_item


def test_manual_adapter_from_items():
    adapter = ManualAdapter()
    items = adapter.fetch(
        {
            "items": [
                {
                    "id": "1",
                    "title": "Engineer",
                    "url": "https://example.com/jobs/1",
                    "company_name": "Acme",
                    "location": "Remote",
                }
            ]
        },
        IngestContext(),
    )
    assert len(items) == 1
    assert items[0].title == "Engineer"
    assert items[0].external_id.startswith("manual:")


def test_manual_adapter_from_file(tmp_path: Path):
    path = tmp_path / "jobs.json"
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Dev",
                        "url": "https://example.com/j",
                        "company": "Beta",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    items = ManualAdapter().fetch({"path": str(path)}, IngestContext())
    assert items[0].company_name == "Beta"


def test_dedupe_key_stable():
    a = RawItem(
        external_id="greenhouse:discord:1",
        title="X",
        url="https://example.com",
        company_name="Discord",
        location="Remote",
        description=None,
        posted_at=None,
        category="employment",
        raw={},
    )
    b = RawItem(
        external_id="greenhouse:discord:1",
        title="Different",
        url="https://example.com/2",
        company_name="Other",
        location=None,
        description=None,
        posted_at=None,
        category="employment",
        raw={},
    )
    assert make_dedupe_key(a) == make_dedupe_key(b)


def test_normalize_sets_live_demo_flag():
    item = RawItem(
        external_id="x",
        title="Role",
        url="https://example.com",
        company_name="Co",
        location="Remote Auckland",
        description=None,
        posted_at=None,
        category="employment",
        raw={},
    )
    norm = normalize_raw_item(item, source_id="s1", source_url="https://example.com")
    assert norm["is_demo"] == 0
    assert norm["remote_ok"] == 1
    assert norm["company_name"] == "Co"
