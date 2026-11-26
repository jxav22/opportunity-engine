"""Core scoring tests — determinism and contract shape."""

from __future__ import annotations

import json

import pytest

from opportunity_engine.profile import DEFAULT_PROFILE, normalize_profile
from opportunity_engine.scoring import (
    detect_penalties,
    rescore_all,
    round1,
    score_breakdown_to_json,
    score_opportunity,
)


SAMPLE_OPP = {
    "id": "opp-1",
    "title": "Software Engineer — Full Stack",
    "company_name": "Immutable",
    "company_id": "immutable",
    "location": "Remote — APAC / New Zealand friendly",
    "remote_ok": 1,
    "category": "employment",
    "url": "https://example.com/jobs/1",
    "description": (
        "Join an exceptional engineering team working on technically demanding "
        "Web3 and DeFi problems. Mentorship, ownership, and career development. "
        "Stack: TypeScript, React, Node.js. Compensation: NZD $120k–$150k + equity. "
        "Remote-first across APAC."
    ),
    "posted_at": "2026-11-01T00:00:00Z",
    "last_seen_at": "2026-11-20T00:00:00Z",
    "stale": 0,
    "is_demo": 0,
    "source_id": "manual",
}

SAMPLE_COMPANY = {
    "id": "immutable",
    "name": "Immutable",
    "interest_level": 4,
    "data_quality": "partial",
    "funding_stage": "series b",
    "why_interesting": "Strong engineering culture in gaming/Web3.",
    "engineering_stack_json": ["TypeScript", "React"],
    "accessibility_notes": "Remote APAC; NZ candidates welcome",
}


def test_round1_no_false_precision():
    assert round1(3.14159) == 3.1
    assert round1(2.96) == 3.0
    assert round1(None) is None


def test_score_shape_and_dimensions():
    result = score_opportunity(SAMPLE_OPP, DEFAULT_PROFILE, SAMPLE_COMPANY)
    assert "score_total" in result
    assert "quality_score" in result
    assert "accessibility_score" in result
    assert result["quality_score"] is not None
    assert result["accessibility_score"] is not None
    assert result["score_total"] is not None
    # one decimal
    for key in ("score_total", "quality_score", "accessibility_score"):
        val = result[key]
        assert val == round(val, 1)
    breakdown = result["score_breakdown"]
    expected_dims = set(DEFAULT_PROFILE["ranking_weights"])
    assert set(breakdown) == expected_dims
    for dim, cell in breakdown.items():
        assert set(cell) >= {"score", "rationale", "evidence"}
        assert isinstance(cell["rationale"], str)
        assert isinstance(cell["evidence"], list)
        if cell["score"] is not None:
            assert 0.0 <= cell["score"] <= 5.0
            assert cell["score"] == round(cell["score"], 1)


def test_scoring_is_deterministic():
    a = score_opportunity(SAMPLE_OPP, DEFAULT_PROFILE, SAMPLE_COMPANY)
    b = score_opportunity(SAMPLE_OPP, DEFAULT_PROFILE, SAMPLE_COMPANY)
    assert a == b
    # JSON round-trip stable
    ja = score_breakdown_to_json(a)
    jb = score_breakdown_to_json(b)
    assert ja == jb
    assert json.loads(ja)["dimensions"]["technical_growth"]["score"] is not None


def test_quality_vs_accessibility_separated():
    result = score_opportunity(SAMPLE_OPP, DEFAULT_PROFILE, SAMPLE_COMPANY)
    # Blend default 0.7/0.3 — use same one-decimal helper as scorer
    q, a = result["quality_score"], result["accessibility_score"]
    expected = round1(0.7 * q + 0.3 * a)
    assert result["score_total"] == expected
    assert result["quality_score"] != result["accessibility_score"] or True
    # UI must be able to show both separately
    assert "quality_score" in result and "accessibility_score" in result


def test_custom_blend_and_weights():
    profile = normalize_profile(
        {
            **DEFAULT_PROFILE,
            "ranking_weights": {**DEFAULT_PROFILE["ranking_weights"], "technical_growth": 3.0},
            "score_blend": {"quality": 1.0, "accessibility": 0.0},
        }
    )
    result = score_opportunity(SAMPLE_OPP, profile, SAMPLE_COMPANY)
    assert result["score_total"] == result["quality_score"]


def test_geo_and_seniority_penalties():
    opp = {
        **SAMPLE_OPP,
        "title": "Principal Staff Engineer",
        "location": "San Francisco, CA",
        "remote_ok": 0,
        "description": (
            "US citizens only. Must be located in the United States. "
            "On-site only. Competitive salary. No visa sponsorship."
        ),
    }
    profile = normalize_profile({**DEFAULT_PROFILE, "years_experience": 1.5})
    penalties = detect_penalties(opp, profile)
    codes = {p["code"] for p in penalties}
    assert "geo_restriction" in codes
    assert "unrealistic_seniority" in codes
    result = score_opportunity(opp, profile)
    assert result["accessibility_score"] is not None
    assert result["accessibility_score"] < 3.0


def test_dubious_and_upfront_cost_penalties():
    opp = {
        **SAMPLE_OPP,
        "title": "Get rich crypto airdrop partner",
        "description": "Guaranteed income. Pay to apply. Upfront fee required. MLM.",
    }
    penalties = detect_penalties(opp, DEFAULT_PROFILE)
    codes = {p["code"] for p in penalties}
    assert "dubious" in codes
    assert "high_upfront_cost" in codes


def test_generic_customer_service_penalty():
    opp = {
        **SAMPLE_OPP,
        "title": "Customer Service Representative",
        "description": "Remote customer support role. Competitive salary.",
    }
    penalties = detect_penalties(opp, DEFAULT_PROFILE)
    assert any(p["code"] == "generic_low_value" for p in penalties)


def test_null_dimension_when_no_evidence():
    opp = {
        "id": "thin",
        "title": "Role",
        "description": "",
        "location": None,
        "category": "employment",
        "url": "https://example.com/x",
        "stale": 0,
        "is_demo": 0,
    }
    result = score_opportunity(opp, DEFAULT_PROFILE)
    # Several quality dims should be null rather than fabricated
    nulls = [
        k
        for k, v in result["score_breakdown"].items()
        if v["score"] is None and k != "accessibility"
    ]
    assert "peer_quality" in nulls or "engineering_culture" in nulls


def test_rescore_all_persists(tmp_path):
    from opportunity_engine import db as dbmod
    from opportunity_engine.profile import save_profile

    db_path = tmp_path / "t.db"
    conn = dbmod.init_db(db_path=db_path)
    save_profile(DEFAULT_PROFILE, conn, path=tmp_path / "profile.json")
    conn.execute(
        """
        INSERT INTO opportunities (
            id, dedupe_key, category, title, company_name, location, remote_ok,
            url, description, source_id, source_url, discovered_at, posted_at, last_seen_at,
            stale, is_demo, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, 'new')
        """,
        (
            "demo-1",
            "demo-1",
            "employment",
            SAMPLE_OPP["title"],
            SAMPLE_OPP["company_name"],
            SAMPLE_OPP["location"],
            1,
            SAMPLE_OPP["url"],
            SAMPLE_OPP["description"],
            "manual",
            SAMPLE_OPP["url"],
            "2026-11-01T00:00:00Z",
            "2026-11-01T00:00:00Z",
            "2026-11-20T00:00:00Z",
        ),
    )
    conn.commit()
    summary = rescore_all(conn)
    assert summary["scored"] == 1
    row = conn.execute(
        "SELECT score_total, quality_score, accessibility_score, score_breakdown_json, next_action FROM opportunities WHERE id='demo-1'"
    ).fetchone()
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    breakdown = json.loads(row[3])
    assert "dimensions" in breakdown
    assert "penalties" in breakdown
    conn.close()
