"""Typed shapes matching the canonical SQLite schema (contracts)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RawItem:
    external_id: str
    title: str
    url: str
    company_name: str | None
    location: str | None
    description: str | None
    posted_at: str | None  # ISO8601
    category: str  # employment | emerging_company | community | entrepreneurial
    raw: dict


@dataclass
class OpportunityRow:
    id: str
    dedupe_key: str
    category: str
    title: str
    company_id: str | None
    company_name: str
    location: str | None
    remote_ok: int | None
    url: str
    description: str | None
    source_id: str
    source_url: str
    discovered_at: str
    posted_at: str | None
    last_seen_at: str
    stale: int = 0
    is_demo: int = 0
    raw_json: str | None = None
    skills_json: str | None = None
    score_total: float | None = None
    score_breakdown_json: str | None = None
    accessibility_score: float | None = None
    quality_score: float | None = None
    next_action: str | None = None
    action_rationale: str | None = None
    uncertainties_json: str | None = None
    why_valuable: str | None = None
    why_relevant: str | None = None
    evidence_summary: str | None = None
    saved: int = 0
    status: str = "new"


@dataclass
class IngestRunRow:
    id: str
    source_id: str
    started_at: str
    finished_at: str | None = None
    status: str = "ok"
    items_seen: int = 0
    items_new: int = 0
    error: str | None = None


@dataclass
class SourceRow:
    id: str
    name: str
    adapter: str
    config_json: str
    enabled: int = 1
    last_success_at: str | None = None
    last_error: str | None = None
    last_attempt_at: str | None = None
    created_at: str = ""
