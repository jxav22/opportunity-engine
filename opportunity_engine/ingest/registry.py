"""Adapter registry."""

from __future__ import annotations

from opportunity_engine.ingest.ashby import AshbyAdapter
from opportunity_engine.ingest.github_releases import GithubReleasesAdapter
from opportunity_engine.ingest.greenhouse import GreenhouseAdapter
from opportunity_engine.ingest.lever import LeverAdapter
from opportunity_engine.ingest.manual import ManualAdapter
from opportunity_engine.ingest.rss import RssAdapter

ADAPTERS = {
    "greenhouse": GreenhouseAdapter(),
    "lever": LeverAdapter(),
    "ashby": AshbyAdapter(),
    "rss": RssAdapter(),
    "github": GithubReleasesAdapter(),
    "manual": ManualAdapter(),
}


def get_adapter(name: str):
    adapter = ADAPTERS.get(name)
    if adapter is None:
        raise KeyError(f"Unknown adapter: {name}")
    return adapter
