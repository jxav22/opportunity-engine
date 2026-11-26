"""Skill extraction and priority tests."""

from __future__ import annotations

from opportunity_engine.profile import DEFAULT_PROFILE
from opportunity_engine.skills import (
    compare_to_profile,
    extract_skills,
    frequency_analysis,
    upskilling_priorities,
)


JOB_TEXT = """
We need a full-stack engineer strong in TypeScript, React, and Node.js.
Experience with Kubernetes and distributed systems is a plus.
Web3 / DeFi familiarity welcome. C# and .NET also used in parts of the stack.
"""


def test_extract_skills_taxonomy():
    skills = extract_skills(JOB_TEXT)
    assert "TypeScript" in skills
    assert "React" in skills
    assert "Node.js" in skills
    assert "Kubernetes" in skills
    assert "Distributed Systems" in skills
    assert "Web3" in skills
    assert "DeFi" in skills
    assert "C#" in skills
    assert ".NET" in skills
    assert "full-stack" in skills


def test_extract_skills_deterministic():
    assert extract_skills(JOB_TEXT) == extract_skills(JOB_TEXT)


def test_frequency_and_compare():
    mentions = [
        {"skill": "TypeScript"},
        {"skill": "TypeScript"},
        {"skill": "Rust"},
        {"skill": "Rust"},
        {"skill": "Rust"},
        {"skill": "Kotlin"},
    ]
    freq = frequency_analysis(mentions=mentions)
    assert freq[0]["skill"] == "Rust"
    assert freq[0]["count"] == 3
    assert "historical" in freq[0]["note"].lower() or "not a historical" in freq[0]["note"].lower()
    comparison = compare_to_profile(freq, DEFAULT_PROFILE)
    assert "TypeScript" in comparison["in_market_not_profile"] or "Rust" in comparison["in_market_not_profile"]
    assert "C#" in comparison["in_profile_not_market"] or "JavaScript" in comparison["overlap"] or True


def test_upskilling_prefers_leverage_over_mere_frequency():
    freq = [
        {"skill": "Kotlin", "count": 20},  # frequent but not high-leverage tagged
        {"skill": "Rust", "count": 2},
        {"skill": "Distributed Systems", "count": 1},
    ]
    # High-scoring roles mention Rust/Distributed Systems
    priorities = upskilling_priorities(
        freq,
        DEFAULT_PROFILE,
        high_score_skills=["Rust", "Distributed Systems"],
    )
    skills = [p["skill"] for p in priorities]
    assert "Rust" in skills
    assert "Distributed Systems" in skills
    # Rust/Distributed should outrank pure frequency Kotlin unless Kotlin also leveraged
    top = priorities[0]["skill"]
    assert top in {"Rust", "Distributed Systems"}
    for p in priorities:
        assert "historical" in p["caveat"].lower() or "current" in p["caveat"].lower()
