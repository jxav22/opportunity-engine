"""Deterministic explainable opportunity ranking."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from opportunity_engine.profile import (
    QUALITY_DIMENSIONS,
    get_ranking_weights,
    load_profile,
    normalize_profile,
)

# Score scale: 0–5 (or null when insufficient evidence).
SCORE_MAX = 5.0

SENIORITY_PATTERNS = [
    (re.compile(r"\b(staff|principal|distinguished|fellow)\b", re.I), 8.0),
    (re.compile(r"\b(senior|sr\.?)\b", re.I), 5.0),
    (re.compile(r"\b(lead|manager|head of|director)\b", re.I), 6.0),
    (re.compile(r"\b(mid[- ]?level|intermediate)\b", re.I), 3.0),
    (re.compile(r"\b(junior|graduate|grad|intern|entry[- ]?level|new grad)\b", re.I), 1.0),
]

GEO_RESTRICT_PATTERNS = [
    re.compile(r"\bmust be (located|based) in\b.{0,40}\b(US|USA|United States|UK|London|EU)\b", re.I),
    re.compile(r"\b(US|USA|United States)\s+(citizens?|residents?)\s+only\b", re.I),
    re.compile(r"\bno (remote|relocation|visa|sponsorship)\b", re.I),
    re.compile(r"\bmust have (the )?right to work in\b.{0,30}\b(US|USA|UK|Australia)\b", re.I),
    re.compile(r"\bon[- ]site only\b", re.I),
]

NZ_FRIENDLY = re.compile(
    r"\b(new zealand|auckland|wellington|christchurch|nz\b|apac|worldwide|anywhere|remote[- ]first)\b",
    re.I,
)
REMOTE_OK = re.compile(r"\b(remote|work from (home|anywhere)|distributed)\b", re.I)

STALE_DAYS_DEFAULT = 45

GENERIC_LOW_VALUE = re.compile(
    r"\b(content moderator|data entry|call centre|call center|commission[- ]only sales)\b",
    re.I,
)
DUBIOUS = re.compile(
    r"\b(get rich|guaranteed income|crypto airdrop|mlm|multi[- ]level)\b", re.I,
)
UPFRONT_COST = re.compile(
    r"\b(pay (to|for) (apply|train|certif)|upfront (fee|cost)|buy[- ]in required)\b",
    re.I,
)
MISLEADING_COMP = re.compile(
    r"\b(unlimited pto|competitive salary(?!\s*(from|of|:|\d))|doe\b)\b",
    re.I,
)

GROWTH_HINTS = re.compile(
    r"\b(mentorship|learning|growth|training|career development|hard problems|"
    r"technically demanding|cutting[- ]edge|research)\b",
    re.I,
)
CULTURE_HINTS = re.compile(
    r"\b(engineering (culture|blog|excellence)|code review|pair programming|"
    r"high[- ]performing team|exceptional engineers?)\b",
    re.I,
)
PEER_HINTS = re.compile(
    r"\b(world[- ]class|top[- ]tier|ex-(google|meta|stripe|amazon)|strong peers|"
    r"talented (engineers?|team))\b",
    re.I,
)
COMP_HINTS = re.compile(
    r"\b(salary|compensation|equity|stock|rsu|nzd|usd|\$\d)",
    re.I,
)
CAREER_HINTS = re.compile(
    r"\b(brand|resume|portfolio|open source|ownership|impact|platform)\b",
    re.I,
)
INDUSTRY_HINTS = re.compile(
    r"\b(fintech|web3|defi|climate|biotech|deeptech|ai|ml|emerging|"
    r"startup|series [a-c])\b",
    re.I,
)
AUTONOMY_HINTS = re.compile(
    r"\b(autonomy|ownership|self[- ]directed|minimal process|trust)\b",
    re.I,
)
LIFESTYLE_HINTS = re.compile(
    r"\b(flexible|work[- ]life|async|timezone|4[- ]day)\b",
    re.I,
)
OPTIONALITY_HINTS = re.compile(
    r"\b(optionality|network|platform|transferable|adjacent domains?)\b",
    re.I,
)
ENTREPRENEUR_HINTS = re.compile(
    r"\b(founding|0[- ]to[- ]1|early[- ]stage|equity[- ]heavy|startup|"
    r"entrepreneur|builder)\b",
    re.I,
)


def round1(value: float | None) -> float | None:
    """One decimal — avoid false precision."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value) + 1e-9, 1)


def _text_blob(opportunity: dict[str, Any], company: dict[str, Any] | None = None) -> str:
    parts = [
        opportunity.get("title") or "",
        opportunity.get("description") or "",
        opportunity.get("location") or "",
        opportunity.get("company_name") or "",
    ]
    if company:
        parts.extend(
            [
                company.get("product_description") or "",
                company.get("industry") or "",
                company.get("why_interesting") or "",
                company.get("accessibility_notes") or "",
                company.get("remote_policy") or "",
                company.get("funding_stage") or "",
            ]
        )
        stack = company.get("engineering_stack_json")
        if isinstance(stack, list):
            parts.append(" ".join(str(s) for s in stack))
        elif isinstance(stack, str):
            parts.append(stack)
    return "\n".join(parts)


def _dim(
    score: float | None,
    rationale: str,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "score": round1(score) if score is not None else None,
        "rationale": rationale,
        "evidence": list(evidence or []),
    }


def _clamp(score: float) -> float:
    return max(0.0, min(SCORE_MAX, score))


def _match_count(pattern: re.Pattern[str], text: str, limit: int = 5) -> list[str]:
    found: list[str] = []
    for m in pattern.finditer(text):
        snippet = m.group(0).strip()
        if snippet and snippet not in found:
            found.append(snippet)
        if len(found) >= limit:
            break
    return found


def score_technical_growth(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = _text_blob(opportunity, company)
    hits = _match_count(GROWTH_HINTS, text)
    skills = [s.lower() for s in (profile.get("skills") or [])]
    skill_hits = [
        s for s in skills if s and re.search(rf"\b{re.escape(s)}\b", text, re.I)
    ]
    if not hits and not skill_hits:
        return _dim(
            None,
            "Insufficient evidence of technical growth opportunity in posting text.",
        )
    base = 2.5 + min(2.0, 0.4 * len(hits)) + min(1.0, 0.3 * len(skill_hits))
    rationale = (
        "Posting signals learning / hard-problem environment"
        if hits
        else "Overlaps profile skills but limited growth language"
    )
    return _dim(_clamp(base), rationale, hits + [f"skill:{s}" for s in skill_hits[:3]])


def score_engineering_culture(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile  # dimension uses text evidence, not profile fields
    text = _text_blob(opportunity, company)
    hits = _match_count(CULTURE_HINTS, text)
    if company and company.get("why_interesting"):
        hits.append("company.why_interesting present")
    if not hits:
        return _dim(None, "No clear engineering-culture signals in available text.")
    return _dim(
        _clamp(2.5 + min(2.5, 0.5 * len(hits))),
        "Engineering culture cues present in posting or company notes.",
        hits,
    )


def score_peer_quality(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(PEER_HINTS, text)
    if not hits:
        return _dim(None, "Peer quality not evidenced in source text.")
    return _dim(
        _clamp(3.0 + min(2.0, 0.5 * len(hits))),
        "Mentions of strong peers or pedigree found.",
        hits,
    )


def score_compensation(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(COMP_HINTS, text)
    if MISLEADING_COMP.search(text) and not re.search(r"\$\d", text):
        return _dim(
            1.5,
            "Compensation language is vague or potentially misleading; no concrete figures.",
            _match_count(MISLEADING_COMP, text) + hits[:2],
        )
    if not hits:
        return _dim(None, "No compensation details disclosed.")
    has_number = bool(re.search(r"\$\s?\d|\d{2,3}\s?k\b", text, re.I))
    score = 3.5 if has_number else 2.5
    return _dim(
        _clamp(score + min(1.0, 0.2 * len(hits))),
        "Compensation signals present"
        + (" with numeric detail." if has_number else " without hard numbers."),
        hits,
    )


def score_career_capital(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(CAREER_HINTS, text)
    interest = (company or {}).get("interest_level") or 0
    if interest:
        hits.append(f"watchlist interest_level={interest}")
    if not hits:
        return _dim(None, "Career-capital transferability not evidenced.")
    bonus = min(1.5, 0.3 * int(interest))
    return _dim(
        _clamp(2.5 + min(2.0, 0.4 * len(hits)) + bonus),
        "Role or company may build transferable career capital.",
        hits,
    )


def score_industry_growth(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = _text_blob(opportunity, company)
    hits = _match_count(INDUSTRY_HINTS, text)
    interests = [i.lower() for i in (profile.get("interests") or [])]
    interest_hits = [
        i
        for i in interests
        if i
        and (
            "emerging" in i
            or "web3" in i
            or "entrepren" in i
            or "technically" in i
        )
        and any(tok in text.lower() for tok in i.split()[:2])
    ]
    if not hits and not interest_hits:
        return _dim(None, "Industry growth posture not clear from text.")
    return _dim(
        _clamp(2.8 + min(2.0, 0.4 * len(hits))),
        "Aligned with emerging / growth industry cues.",
        hits + [f"interest:{i}" for i in interest_hits[:2]],
    )


def score_autonomy(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(AUTONOMY_HINTS, text)
    if not hits:
        return _dim(None, "Autonomy not mentioned in available evidence.")
    return _dim(
        _clamp(3.0 + min(2.0, 0.4 * len(hits))),
        "Autonomy / ownership language present.",
        hits,
    )


def score_lifestyle(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(LIFESTYLE_HINTS, text)
    remote = opportunity.get("remote_ok")
    if remote == 1 or remote is True:
        hits.append("remote_ok=1")
    if not hits:
        return _dim(None, "Lifestyle / flexibility not evidenced.")
    return _dim(
        _clamp(2.5 + min(2.5, 0.5 * len(hits))),
        "Flexibility or remote-friendly signals found.",
        hits,
    )


def score_optionality(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(OPTIONALITY_HINTS, text)
    cat = (opportunity.get("category") or "").lower()
    if cat in {"emerging_company", "entrepreneurial", "community"}:
        hits.append(f"category={cat}")
    if not hits:
        return _dim(None, "Optionality not clearly supported by evidence.")
    return _dim(
        _clamp(2.5 + min(2.5, 0.5 * len(hits))),
        "Path preserves or expands future optionality.",
        hits,
    )


def score_entrepreneurial_upside(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    text = _text_blob(opportunity, company)
    hits = _match_count(ENTREPRENEUR_HINTS, text)
    stage = ((company or {}).get("funding_stage") or "").lower()
    if stage and any(s in stage for s in ("pre-seed", "seed", "series a", "angel")):
        hits.append(f"funding_stage={stage}")
    cat = (opportunity.get("category") or "").lower()
    if cat == "entrepreneurial":
        hits.append("category=entrepreneurial")
    if not hits:
        return _dim(None, "Entrepreneurial upside not evidenced.")
    return _dim(
        _clamp(3.0 + min(2.0, 0.4 * len(hits))),
        "Early-stage or builder upside signals present.",
        hits,
    )


def score_evidence_strength(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile
    evidence: list[str] = []
    score = 1.0
    desc = opportunity.get("description") or ""
    if len(desc) >= 400:
        score += 1.5
        evidence.append("description length ≥ 400 chars")
    elif len(desc) >= 120:
        score += 0.8
        evidence.append("description length ≥ 120 chars")
    else:
        evidence.append("short or missing description")
    if opportunity.get("url"):
        score += 0.5
        evidence.append("source url present")
    if opportunity.get("posted_at"):
        score += 0.4
        evidence.append(f"posted_at={opportunity['posted_at']}")
    if company and company.get("data_quality") == "verified":
        score += 1.0
        evidence.append("company.data_quality=verified")
    elif company and company.get("data_quality") == "partial":
        score += 0.4
        evidence.append("company.data_quality=partial")
    if opportunity.get("is_demo") in (1, True):
        score -= 0.5
        evidence.append("is_demo=1 (bundled sample)")
    if not evidence:
        return _dim(None, "No provenance fields available.")
    return _dim(
        _clamp(score),
        "Evidence strength based on description depth and provenance fields.",
        evidence,
    )


def score_accessibility_dimension(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Accessibility as a quality-table dimension (also feeds accessibility_score)."""
    result = compute_accessibility(opportunity, profile, company)
    return _dim(result["score"], result["rationale"], result["evidence"])


DIMENSION_SCORERS = {
    "technical_growth": score_technical_growth,
    "engineering_culture": score_engineering_culture,
    "peer_quality": score_peer_quality,
    "compensation": score_compensation,
    "accessibility": score_accessibility_dimension,
    "career_capital": score_career_capital,
    "industry_growth": score_industry_growth,
    "autonomy": score_autonomy,
    "lifestyle": score_lifestyle,
    "optionality": score_optionality,
    "entrepreneurial_upside": score_entrepreneurial_upside,
    "evidence_strength": score_evidence_strength,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_accessibility(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Geo / visa / seniority fit — separate from quality."""
    text = _text_blob(opportunity, company)
    evidence: list[str] = []
    score = 3.0
    rationale_bits: list[str] = []

    years = float(profile.get("years_experience") or 0)
    required = None
    for pattern, need in SENIORITY_PATTERNS:
        if pattern.search(text) or pattern.search(opportunity.get("title") or ""):
            required = need
            evidence.append(f"seniority cue → ~{need}+ years signal")
            break
    if required is not None:
        gap = required - years
        if gap >= 4:
            score -= 2.5
            rationale_bits.append("seniority looks unrealistic vs profile experience")
        elif gap >= 2:
            score -= 1.2
            rationale_bits.append("seniority stretch vs profile experience")
        elif gap <= 0:
            score += 0.5
            rationale_bits.append("seniority roughly fits experience")
        else:
            rationale_bits.append("modest seniority stretch")

    geo_hits = []
    for pat in GEO_RESTRICT_PATTERNS:
        geo_hits.extend(_match_count(pat, text, limit=2))
    if geo_hits:
        score -= 2.0
        evidence.extend(geo_hits)
        rationale_bits.append("geo / work-authorization restrictions detected")
    elif NZ_FRIENDLY.search(text) or NZ_FRIENDLY.search(opportunity.get("location") or ""):
        score += 1.0
        evidence.append("NZ / APAC / worldwide friendly cue")
        rationale_bits.append("location language friendly to NZ-based candidate")
    elif opportunity.get("remote_ok") in (1, True) or REMOTE_OK.search(text):
        score += 0.8
        evidence.append("remote-friendly")
        rationale_bits.append("remote-friendly posting")
    elif opportunity.get("location"):
        evidence.append(f"location={opportunity['location']}")
        if profile.get("willing_to_relocate"):
            rationale_bits.append("non-local role; relocate willingness noted")
        else:
            score -= 0.8
            rationale_bits.append("non-local role without clear remote/NZ fit")

    notes = (company or {}).get("accessibility_notes")
    if notes:
        evidence.append(f"accessibility_notes: {notes[:120]}")
        if re.search(r"\b(visa|sponsor|nz|remote)\b", notes, re.I):
            score += 0.3

    if not rationale_bits:
        rationale_bits.append("Limited accessibility evidence; mid default.")

    return {
        "score": round1(_clamp(score)),
        "rationale": " ".join(rationale_bits),
        "evidence": evidence,
    }


def detect_penalties(
    opportunity: dict[str, Any],
    profile: dict[str, Any],
    company: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
    stale_days: int = STALE_DAYS_DEFAULT,
) -> list[dict[str, Any]]:
    """Explicit negative adjustments with reasons (not buried in dimensions)."""
    text = _text_blob(opportunity, company)
    penalties: list[dict[str, Any]] = []
    now = now or datetime.now(timezone.utc)

    for pat in GEO_RESTRICT_PATTERNS:
        hits = _match_count(pat, text, limit=1)
        if hits:
            penalties.append(
                {
                    "code": "geo_restriction",
                    "amount": -1.0,
                    "reason": "Geographic or work-authorization restriction.",
                    "evidence": hits,
                }
            )
            break

    years = float(profile.get("years_experience") or 0)
    for pattern, need in SENIORITY_PATTERNS:
        title = opportunity.get("title") or ""
        if pattern.search(title) or pattern.search(text):
            if need - years >= 4:
                penalties.append(
                    {
                        "code": "unrealistic_seniority",
                        "amount": -1.2,
                        "reason": "Seniority bar looks unrealistic for profile experience.",
                        "evidence": [title or hits_safe(pattern, text)],
                    }
                )
            break

    if opportunity.get("stale") in (1, True):
        penalties.append(
            {
                "code": "stale",
                "amount": -0.8,
                "reason": "Marked stale by ingest.",
                "evidence": ["stale=1"],
            }
        )
    else:
        posted = _parse_dt(opportunity.get("posted_at")) or _parse_dt(
            opportunity.get("last_seen_at")
        )
        if posted and (now - posted).days >= stale_days:
            penalties.append(
                {
                    "code": "stale",
                    "amount": -0.8,
                    "reason": f"Posting older than {stale_days} days.",
                    "evidence": [f"posted_or_seen={posted.date().isoformat()}"],
                }
            )

    desc = opportunity.get("description") or ""
    if len(desc) < 80 and not (company and company.get("data_quality") == "verified"):
        penalties.append(
            {
                "code": "weak_evidence",
                "amount": -0.5,
                "reason": "Thin description / weak evidence base.",
                "evidence": [f"description_len={len(desc)}"],
            }
        )

    if DUBIOUS.search(text):
        penalties.append(
            {
                "code": "dubious",
                "amount": -2.0,
                "reason": "Dubious or scam-like language.",
                "evidence": _match_count(DUBIOUS, text),
            }
        )

    if GENERIC_LOW_VALUE.search(text) or GENERIC_LOW_VALUE.search(
        opportunity.get("title") or ""
    ):
        penalties.append(
            {
                "code": "generic_low_value",
                "amount": -1.0,
                "reason": "Generic low-leverage role pattern.",
                "evidence": _match_count(GENERIC_LOW_VALUE, text)
                or [opportunity.get("title") or ""],
            }
        )

    if MISLEADING_COMP.search(text) and not re.search(r"\$\d", text):
        penalties.append(
            {
                "code": "misleading_comp",
                "amount": -0.4,
                "reason": "Compensation claims lack concrete figures.",
                "evidence": _match_count(MISLEADING_COMP, text),
            }
        )

    if UPFRONT_COST.search(text):
        penalties.append(
            {
                "code": "high_upfront_cost",
                "amount": -2.0,
                "reason": "High upfront cost / pay-to-play signal.",
                "evidence": _match_count(UPFRONT_COST, text),
            }
        )

    return penalties


def hits_safe(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(0) if m else "seniority"


def weighted_mean(
    breakdown: dict[str, dict[str, Any]],
    weights: dict[str, float],
    dimensions: tuple[str, ...] | list[str],
) -> float | None:
    total_w = 0.0
    total = 0.0
    for dim in dimensions:
        cell = breakdown.get(dim) or {}
        score = cell.get("score")
        if score is None:
            continue
        w = float(weights.get(dim, 1.0))
        total += float(score) * w
        total_w += w
    if total_w <= 0:
        return None
    return round1(total / total_w)


def score_opportunity(
    opportunity: dict[str, Any],
    profile: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Return explainable ranking payload:
      dimensions, penalties, quality_score, accessibility_score, score_total
    """
    profile = normalize_profile(profile)
    weights = get_ranking_weights(profile)
    breakdown: dict[str, dict[str, Any]] = {}
    for dim, fn in DIMENSION_SCORERS.items():
        breakdown[dim] = fn(opportunity, profile, company)

    penalties = detect_penalties(opportunity, profile, company, now=now)
    quality = weighted_mean(breakdown, weights, QUALITY_DIMENSIONS)
    accessibility = breakdown["accessibility"]["score"]
    # Prefer dedicated accessibility computation already stored on dimension.
    if accessibility is None:
        accessibility = compute_accessibility(opportunity, profile, company)["score"]

    penalty_sum = sum(float(p["amount"]) for p in penalties)
    if quality is not None:
        quality = round1(_clamp(quality + penalty_sum * 0.5))
    if accessibility is not None and any(
        p["code"] in {"geo_restriction", "unrealistic_seniority"} for p in penalties
    ):
        accessibility = round1(
            _clamp(
                float(accessibility)
                + sum(
                    float(p["amount"])
                    for p in penalties
                    if p["code"] in {"geo_restriction", "unrealistic_seniority"}
                )
                * 0.3
            )
        )

    blend = profile.get("score_blend") or {"quality": 0.7, "accessibility": 0.3}
    wq = float(blend.get("quality", 0.7))
    wa = float(blend.get("accessibility", 0.3))
    if quality is None and accessibility is None:
        score_total = None
    elif quality is None:
        score_total = round1(float(accessibility))
    elif accessibility is None:
        score_total = round1(float(quality))
    else:
        denom = wq + wa
        score_total = round1((wq * float(quality) + wa * float(accessibility)) / denom)

    return {
        "score_total": score_total,
        "quality_score": quality,
        "accessibility_score": accessibility,
        "score_breakdown": breakdown,
        "penalties": penalties,
        "weights_used": {k: round1(v) for k, v in weights.items()},
        "blend": {"quality": wq, "accessibility": wa},
    }


def score_breakdown_to_json(result: dict[str, Any]) -> str:
    """Serialize breakdown (+ penalties) for opportunities.score_breakdown_json."""
    payload = {
        "dimensions": result.get("score_breakdown") or {},
        "penalties": result.get("penalties") or [],
        "blend": result.get("blend") or {},
        "weights_used": result.get("weights_used") or {},
    }
    return json.dumps(payload, ensure_ascii=False)


def _row_to_dict(row: sqlite3.Row | tuple, cursor: sqlite3.Cursor) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def _load_company(
    conn: sqlite3.Connection, company_id: str | None
) -> dict[str, Any] | None:
    if not company_id:
        return None
    cur = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    row = cur.fetchone()
    if not row:
        return None
    data = _row_to_dict(row, cur)
    stack = data.get("engineering_stack_json")
    if isinstance(stack, str) and stack:
        try:
            data["engineering_stack_json"] = json.loads(stack)
        except json.JSONDecodeError:
            pass
    return data


def score_and_persist(
    conn: sqlite3.Connection,
    opportunity_id: str,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,))
    row = cur.fetchone()
    if not row:
        return None
    opp = _row_to_dict(row, cur)
    company = _load_company(conn, opp.get("company_id"))
    profile = profile or load_profile(conn)
    result = score_opportunity(opp, profile, company)

    # Optional enrichment from sibling modules (lazy to keep scoring credential-free).
    try:
        from opportunity_engine.skills import extract_and_store_skills

        skills = extract_and_store_skills(conn, opp, company)
        result["skills"] = skills
    except Exception:
        skills = []

    try:
        from opportunity_engine.actions import recommend_action

        action = recommend_action(opp, result, profile, company)
        result["action"] = action
    except Exception:
        action = {}

    conn.execute(
        """
        UPDATE opportunities SET
            score_total = ?,
            quality_score = ?,
            accessibility_score = ?,
            score_breakdown_json = ?,
            skills_json = COALESCE(?, skills_json),
            next_action = COALESCE(?, next_action),
            action_rationale = COALESCE(?, action_rationale),
            why_valuable = COALESCE(?, why_valuable),
            why_relevant = COALESCE(?, why_relevant),
            evidence_summary = COALESCE(?, evidence_summary),
            uncertainties_json = COALESCE(?, uncertainties_json)
        WHERE id = ?
        """,
        (
            result.get("score_total"),
            result.get("quality_score"),
            result.get("accessibility_score"),
            score_breakdown_to_json(result),
            json.dumps(skills, ensure_ascii=False) if skills else None,
            action.get("next_action"),
            action.get("action_rationale"),
            action.get("why_valuable"),
            action.get("why_relevant"),
            action.get("evidence_summary"),
            json.dumps(action.get("uncertainties") or [], ensure_ascii=False)
            if action
            else None,
            opportunity_id,
        ),
    )
    return result


def rescore_all(
    conn: sqlite3.Connection | None = None,
    *,
    db_path: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """CLI/function: rescore every opportunity after ingest."""
    owns_conn = False
    if conn is None:
        from opportunity_engine import db as dbmod

        conn = dbmod.connect(db_path)
        owns_conn = True
    try:
        profile = profile or load_profile(conn)
        cur = conn.execute("SELECT id FROM opportunities ORDER BY id")
        ids = [r[0] for r in cur.fetchall()]
        scored = 0
        for oid in ids:
            if score_and_persist(conn, oid, profile=profile) is not None:
                scored += 1
        try:
            from opportunity_engine.signals import refresh_signals

            signals = refresh_signals(conn, profile=profile)
        except Exception:
            signals = []
        conn.commit()
        return {"scored": scored, "signals_upserted": len(signals)}
    finally:
        if owns_conn and conn is not None:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Rescore all opportunities")
    parser.add_argument("--db", default=None, help="Path to SQLite DB")
    args = parser.parse_args(argv)
    summary = rescore_all(db_path=args.db)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
