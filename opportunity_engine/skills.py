"""Skill extraction, frequency analysis, and upskilling priorities."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

# Curated taxonomy: canonical name → aliases / patterns (case-insensitive).
SKILL_TAXONOMY: dict[str, list[str]] = {
    "C#": [r"c\#", r"c-sharp", r"csharp"],
    ".NET": [r"\.net", r"dotnet", r"asp\.net"],
    "JavaScript": [r"javascript", r"\bjs\b", r"ecmascript"],
    "TypeScript": [r"typescript", r"\bts\b"],
    "Python": [r"\bpython\b"],
    "Go": [r"\bgolang\b", r"\bgo\b"],
    "Rust": [r"\brust\b"],
    "Java": [r"\bjava\b"],
    "Kotlin": [r"\bkotlin\b"],
    "Swift": [r"\bswift\b"],
    "React": [r"\breact\b", r"react\.js", r"reactjs"],
    "Node.js": [r"node\.js", r"\bnodejs\b", r"\bnode\b"],
    "full-stack": [r"full[- ]stack", r"fullstack"],
    "mobile": [r"\bmobile\b", r"react native", r"ios", r"android"],
    "Web3": [r"\bweb3\b", r"blockchain"],
    "DeFi": [r"\bdefi\b", r"decentrali[sz]ed finance"],
    "Solidity": [r"\bsolidity\b"],
    "AWS": [r"\baws\b", r"amazon web services"],
    "GCP": [r"\bgcp\b", r"google cloud"],
    "Azure": [r"\bazure\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Docker": [r"\bdocker\b"],
    "PostgreSQL": [r"\bpostgres(ql)?\b"],
    "SQL": [r"\bsql\b"],
    "GraphQL": [r"\bgraphql\b"],
    "gRPC": [r"\bgrpc\b"],
    "Machine Learning": [r"machine learning", r"\bml\b", r"\bai\b"],
    "Distributed Systems": [r"distributed systems?"],
    "System Design": [r"system design"],
    "DevOps": [r"\bdevops\b", r"sre\b", r"platform engineering"],
    "Security": [r"\bsecurity\b", r"appsec", r"cybersecurity"],
    "Product": [r"product[- ]minded", r"product engineering"],
}

# Light heuristic noun-ish tokens that look like tech skills (secondary).
_HEURISTIC = re.compile(
    r"\b([A-Z][a-zA-Z0-9+#.]{1,24}|[a-z]+(?:\.js|DB|SQL))\b"
)
_HEURISTIC_STOP = {
    "The",
    "And",
    "With",
    "For",
    "Our",
    "You",
    "Your",
    "This",
    "That",
    "Will",
    "Have",
    "From",
    "About",
    "Role",
    "Team",
    "Company",
    "Job",
    "Work",
    "Remote",
    "Full",
    "Time",
    "New",
    "Zealand",
    "Senior",
    "Junior",
    "Engineer",
    "Engineering",
    "Software",
    "Developer",
    "Experience",
    "Years",
    "Must",
    "Should",
    "Please",
    "Apply",
}


def _compiled_taxonomy() -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    for canonical, patterns in SKILL_TAXONOMY.items():
        combined = "|".join(f"(?:{p})" for p in patterns)
        out.append((canonical, re.compile(combined, re.I)))
    return out


_TAXONOMY_COMPILED = _compiled_taxonomy()


def extract_skills(text: str, *, use_heuristics: bool = True) -> list[str]:
    """Extract normalized skills from job text via curated taxonomy + light heuristics."""
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for canonical, pattern in _TAXONOMY_COMPILED:
        if pattern.search(text) and canonical not in seen:
            seen.add(canonical)
            found.append(canonical)

    if use_heuristics:
        taxonomy_lower = {k.lower() for k in SKILL_TAXONOMY}
        for m in _HEURISTIC.finditer(text):
            token = m.group(1)
            if token in _HEURISTIC_STOP:
                continue
            if token.lower() in taxonomy_lower:
                continue
            # Prefer tokens that appear near engineering context.
            start = max(0, m.start() - 40)
            window = text[start : m.end() + 40].lower()
            if not any(
                k in window
                for k in ("experience", "proficien", "stack", "skill", "using", "with")
            ):
                continue
            # Keep shortlist small — quality over volume.
            if len(found) >= 25:
                break
            label = token if not token.islower() else token
            if label not in seen and label.lower() not in {s.lower() for s in seen}:
                # Only accept heuristic if it looks like a known-ish tech token
                if re.search(r"[A-Z]|#|\.|js|sql|db", token):
                    seen.add(label)
                    found.append(label)
    return found


def extract_skills_from_opportunity(
    opportunity: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> list[str]:
    parts = [
        opportunity.get("title") or "",
        opportunity.get("description") or "",
    ]
    if company:
        parts.append(company.get("product_description") or "")
        stack = company.get("engineering_stack_json")
        if isinstance(stack, list):
            parts.append(" ".join(str(s) for s in stack))
        elif isinstance(stack, str):
            parts.append(stack)
    # Prefer taxonomy hits; include stack entries verbatim normalized via taxonomy.
    skills = extract_skills("\n".join(parts))
    return skills


def skill_mention_id(skill: str, opportunity_id: str) -> str:
    raw = f"{skill.lower()}::{opportunity_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def write_skill_mentions(
    conn: sqlite3.Connection,
    opportunity: dict[str, Any],
    skills: list[str],
    *,
    mentioned_at: str | None = None,
) -> int:
    """Upsert skill_mentions rows; return count written."""
    now = mentioned_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = 0
    for skill in skills:
        mid = skill_mention_id(skill, opportunity["id"])
        conn.execute(
            """
            INSERT INTO skill_mentions (id, skill, opportunity_id, company_id, mentioned_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                skill = excluded.skill,
                mentioned_at = excluded.mentioned_at
            """,
            (
                mid,
                skill,
                opportunity["id"],
                opportunity.get("company_id"),
                now,
            ),
        )
        written += 1
    return written


def extract_and_store_skills(
    conn: sqlite3.Connection,
    opportunity: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> list[str]:
    skills = extract_skills_from_opportunity(opportunity, company)
    if skills:
        write_skill_mentions(conn, opportunity, skills)
        conn.execute(
            "UPDATE opportunities SET skills_json = ? WHERE id = ?",
            (json.dumps(skills, ensure_ascii=False), opportunity["id"]),
        )
    return skills


def frequency_analysis(
    conn: sqlite3.Connection | None = None,
    *,
    mentions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Skill frequency across mentions.
    Does NOT claim historical trends without history — only current corpus counts.
    """
    counter: Counter[str] = Counter()
    if mentions is not None:
        for m in mentions:
            counter[m["skill"]] += 1
    elif conn is not None:
        for row in conn.execute("SELECT skill FROM skill_mentions"):
            counter[row[0]] += 1
    total = sum(counter.values()) or 1
    return [
        {
            "skill": skill,
            "count": count,
            "share": round(count / total, 3),
            "note": "Current corpus frequency only — not a historical trend.",
        }
        for skill, count in counter.most_common()
    ]


def compare_to_profile(
    skills_or_freq: list[str] | list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    profile_skills = [str(s) for s in (profile.get("skills") or [])]
    profile_norm = {s.lower(): s for s in profile_skills}

    if skills_or_freq and isinstance(skills_or_freq[0], dict):
        market = [str(x["skill"]) for x in skills_or_freq]  # type: ignore[index]
        freq_map = {str(x["skill"]): int(x["count"]) for x in skills_or_freq}  # type: ignore[index]
    else:
        market = [str(s) for s in skills_or_freq]  # type: ignore[arg-type]
        freq_map = Counter(market)

    market_norm = {s.lower(): s for s in market}
    overlap = sorted(profile_norm[k] for k in profile_norm.keys() & market_norm.keys())
    missing_from_profile = sorted(
        market_norm[k] for k in market_norm.keys() - profile_norm.keys()
    )
    unused_profile = sorted(
        profile_norm[k] for k in profile_norm.keys() - market_norm.keys()
    )
    return {
        "overlap": overlap,
        "in_market_not_profile": missing_from_profile,
        "in_profile_not_market": unused_profile,
        "frequency": [
            {"skill": s, "count": int(freq_map.get(s, 0))}
            for s in missing_from_profile
        ],
    }


HIGH_LEVERAGE_SKILLS = {
    "Distributed Systems",
    "System Design",
    "Rust",
    "Go",
    "TypeScript",
    "Kubernetes",
    "Machine Learning",
    "Security",
    "Web3",
    "DeFi",
    "Solidity",
    "gRPC",
}


def upskilling_priorities(
    freq: list[dict[str, Any]],
    profile: dict[str, Any],
    *,
    high_score_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Prioritize skills that appear in high-leverage desirable roles,
    not merely the most frequent mentions.
    """
    profile_norm = {str(s).lower() for s in (profile.get("skills") or [])}
    high_set = {s.lower() for s in (high_score_skills or [])}
    priorities: list[dict[str, Any]] = []
    for item in freq:
        skill = str(item["skill"])
        if skill.lower() in profile_norm:
            continue
        count = int(item.get("count") or 0)
        leverage = 0.0
        reasons: list[str] = []
        if skill in HIGH_LEVERAGE_SKILLS or skill.lower() in {
            s.lower() for s in HIGH_LEVERAGE_SKILLS
        }:
            leverage += 2.0
            reasons.append("tagged high-leverage in taxonomy")
        if skill.lower() in high_set:
            leverage += 2.5
            reasons.append("appears in high-scoring / desirable roles")
        # Mild frequency contribution — never dominate.
        leverage += min(1.0, 0.15 * count)
        if count >= 3 and not reasons:
            reasons.append("frequent in corpus (frequency alone — weak signal)")
        if leverage < 1.0 and skill.lower() not in high_set:
            continue
        priorities.append(
            {
                "skill": skill,
                "priority_score": round(leverage, 1),
                "count": count,
                "rationale": "; ".join(reasons)
                or "Moderate demand outside current profile.",
                "caveat": "Not a historical trend — based on current opportunity set only.",
            }
        )
    priorities.sort(key=lambda x: (-x["priority_score"], -x["count"], x["skill"]))
    return priorities[:15]


def skills_radar(
    conn: sqlite3.Connection,
    profile: dict[str, Any],
) -> dict[str, Any]:
    freq = frequency_analysis(conn)
    comparison = compare_to_profile(freq, profile)
    # Skills from higher-scored opportunities (desirable), if scores exist.
    high_skills: list[str] = []
    cur = conn.execute(
        """
        SELECT skills_json FROM opportunities
        WHERE score_total IS NOT NULL AND score_total >= 3.5
          AND skills_json IS NOT NULL
        """
    )
    for (raw,) in cur.fetchall():
        try:
            high_skills.extend(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            continue
    priorities = upskilling_priorities(freq, profile, high_score_skills=high_skills)
    return {
        "frequency": freq,
        "comparison": comparison,
        "upskilling_priorities": priorities,
    }
