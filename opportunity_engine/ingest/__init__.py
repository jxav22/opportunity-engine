"""Source adapters and ingestion pipeline — owned by Agent A."""

from opportunity_engine.ingest.base import IngestContext, RawItem, SourceAdapter
from opportunity_engine.ingest.pipeline import ingest_source, normalize_raw_item
from opportunity_engine.ingest.registry import ADAPTERS, get_adapter

__all__ = [
    "ADAPTERS",
    "IngestContext",
    "RawItem",
    "SourceAdapter",
    "get_adapter",
    "ingest_source",
    "normalize_raw_item",
]
