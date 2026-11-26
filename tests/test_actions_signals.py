"""Actions + signals smoke tests."""

from __future__ import annotations

from opportunity_engine.actions import ACTIONS, recommend_action
from opportunity_engine.profile import DEFAULT_PROFILE
from opportunity_engine.scoring import score_opportunity
from opportunity_engine.signals import refresh_signals


def test_recommend_apply_for_strong_nz_role():
    opp = {
        "id": "a1",
        "title": "Software Engineer",
        "category": "employment",
        "location": "Auckland, New Zealand",
        "remote_ok": 1,
        "url": "https://example.com/a",
        "description": (
            "Technically demanding full-stack role with mentorship, ownership, "
            "TypeScript, and compensation NZD $130k. Exceptional engineering team."
        ),
        "posted_at": "2026-11-10T00:00:00Z",
        "stale": 0,
        "is_demo": 0,
        "company_name": "Halter",
    }
    company = {"id": "halter", "interest_level": 5, "data_quality": "partial"}
    result = score_opportunity(opp, DEFAULT_PROFILE, company)
    action = recommend_action(opp, result, DEFAULT_PROFILE, company)
    assert action["skipped"] is False
    assert action["next_action"] in ACTIONS
    assert "auto-apply" in action["action_rationale"].lower() or "never auto" in action["action_rationale"].lower()
    assert action["why_valuable"]
    assert action["why_relevant"]
    assert action["evidence_summary"]
    assert isinstance(action["uncertainties"], list)


def test_signals_dedupe(tmp_path):
    from opportunity_engine import db as dbmod

    conn = dbmod.init_db(db_path=tmp_path / "s.db")
    conn.execute(
        """
            INSERT INTO opportunities (
                id, dedupe_key, category, title, company_id, company_name, location,
                remote_ok, url, description, source_id, source_url, discovered_at, posted_at,
                last_seen_at, stale, is_demo, status
            ) VALUES (
                'nz1', 'nz1', 'employment', 'Backend Engineer', 'partly', 'Partly',
                'Auckland, New Zealand', 1, 'https://example.com/nz',
                'Hiring in Auckland for TypeScript engineers.', 'manual',
                'https://example.com/nz',
                '2026-11-15T00:00:00Z', '2026-11-15T00:00:00Z', '2026-11-15T00:00:00Z',
                0, 1, 'new'
            )
        """
    )
    conn.commit()
    first = refresh_signals(conn, DEFAULT_PROFILE, strength_threshold=0.55)
    second = refresh_signals(conn, DEFAULT_PROFILE, strength_threshold=0.55)
    assert any(s["kind"] == "nz_hiring" for s in first)
    assert second == []  # deduped
    conn.close()
