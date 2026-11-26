"""Validate seeded sources.json shape and known-good adapters."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "sources.json"

REQUIRED_ADAPTERS = {"greenhouse", "lever", "ashby", "rss", "manual", "github"}


def test_sources_json_well_formed():
    data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    sources = data["sources"]
    assert sources
    ids = [s["id"] for s in sources]
    assert len(ids) == len(set(ids)), "duplicate source ids"
    enabled = [s for s in sources if int(s.get("enabled", 0)) == 1]
    assert len(enabled) >= 10
    for src in sources:
        assert src["adapter"] in REQUIRED_ADAPTERS
        assert isinstance(src["config"], dict)
        assert src["name"]


def test_net_new_coverage_present():
    data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data["sources"]}
    # NZ employment boards
    for sid in ("ashby-auror", "ashby-xero", "ashby-tracksuit", "ashby-kernel"):
        assert int(by_id[sid]["enabled"]) == 1
    # Elite / remote eng
    for sid in ("gh-anthropic", "gh-cloudflare", "gh-vercel", "ashby-linear", "ashby-cursor"):
        assert int(by_id[sid]["enabled"]) == 1
    # Community + entrepreneurial
    assert int(by_id["rss-show-hn"]["enabled"]) == 1
    assert by_id["rss-show-hn"]["config"]["category"] == "community"
    assert int(by_id["rss-antler"]["enabled"]) == 1
    assert by_id["rss-antler"]["config"]["category"] == "entrepreneurial"
    assert int(by_id["rss-yc-blog"]["enabled"]) == 1
    # Known failures stay disabled
    assert int(by_id["rss-rnz-tech"]["enabled"]) == 0
    assert int(by_id["rss-creative-hq"]["enabled"]) == 0
