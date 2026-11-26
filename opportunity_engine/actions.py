"""Next-action recommendations for high-priority opportunities.

Never auto-contact or auto-apply — human-in-the-loop only.
"""

from __future__ import annotations

import json
from typing import Any

# Allowed action vocabulary (contracts / product).
ACTIONS = (
    "Apply",
    "Investigate",
    "Monitor",
    "Attend",
    "Learn",
    "Build",
    "Introduce",
    "OSS",
)

HIGH_PRIORITY_TOTAL = 3.5
HIGH_PRIORITY_QUALITY = 3.8


def _uncertainties(
    opportunity: dict[str, Any],
    score_result: dict[str, Any],
    company: dict[str, Any] | None,
) -> list[str]:
    out: list[str] = []
    breakdown = score_result.get("score_breakdown") or {}
    null_dims = [k for k, v in breakdown.items() if (v or {}).get("score") is None]
    if null_dims:
        out.append(f"Missing evidence for: {', '.join(null_dims[:6])}")
    if not (opportunity.get("description") or "").strip():
        out.append("No job description body — ranking relies on title/metadata.")
    if company is None:
        out.append("No linked company record.")
    elif (company.get("data_quality") or "") == "demo":
        out.append("Company data quality is demo.")
    elif (company.get("data_quality") or "") == "partial":
        out.append("Company data is partial / unverified.")
    if opportunity.get("is_demo") in (1, True):
        out.append("Bundled demo opportunity — not live ingest.")
    for p in score_result.get("penalties") or []:
        out.append(f"Penalty: {p.get('reason')}")
    return out


def _evidence_summary(
    opportunity: dict[str, Any],
    score_result: dict[str, Any],
) -> str:
    bits: list[str] = []
    if opportunity.get("url"):
        bits.append(f"url={opportunity['url']}")
    if opportunity.get("posted_at"):
        bits.append(f"posted_at={opportunity['posted_at']}")
    if opportunity.get("source_id"):
        bits.append(f"source={opportunity['source_id']}")
    penalties = score_result.get("penalties") or []
    if penalties:
        bits.append("penalties=" + ",".join(p["code"] for p in penalties))
    # Pull a few dimension evidence snippets
    breakdown = score_result.get("score_breakdown") or {}
    for dim in ("evidence_strength", "technical_growth", "accessibility"):
        cell = breakdown.get(dim) or {}
        for e in (cell.get("evidence") or [])[:2]:
            bits.append(f"{dim}:{e}")
    return "; ".join(bits) if bits else "Limited provenance fields."


def choose_action(
    opportunity: dict[str, Any],
    score_result: dict[str, Any],
    profile: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
) -> str:
    category = (opportunity.get("category") or "").lower()
    total = score_result.get("score_total")
    quality = score_result.get("quality_score")
    accessibility = score_result.get("accessibility_score")
    title = (opportunity.get("title") or "").lower()
    desc = (opportunity.get("description") or "").lower()
    blob = f"{title}\n{desc}"

    if category == "community" or "meetup" in blob or "conference" in blob:
        return "Attend"
    if category == "entrepreneurial" or "accelerator" in blob:
        return "Build" if "build" in blob or "founder" in blob else "Investigate"
    if "open source" in blob or "oss" in blob or "github.com" in blob:
        return "OSS"
    if "learn" in blob or "course" in blob or "upskill" in blob:
        return "Learn"
    if company and int(company.get("interest_level") or 0) >= 4 and (
        total is None or float(total) < HIGH_PRIORITY_TOTAL
    ):
        return "Monitor"
    if accessibility is not None and float(accessibility) < 2.0:
        return "Investigate"
    if total is not None and float(total) >= HIGH_PRIORITY_TOTAL:
        if category == "employment" and (
            accessibility is None or float(accessibility) >= 2.5
        ):
            return "Apply"
        return "Investigate"
    if quality is not None and float(quality) >= HIGH_PRIORITY_QUALITY:
        return "Investigate"
    if company and int(company.get("interest_level") or 0) >= 3:
        return "Monitor"
    # Soft network action when peer/community language exists
    if "introduc" in blob or "referral" in blob:
        return "Introduce"
    return "Monitor"


def recommend_action(
    opportunity: dict[str, Any],
    score_result: dict[str, Any],
    profile: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Fill next_action fields for high-priority ops (or when force=True).
    Never auto-contact / auto-apply.
    """
    total = score_result.get("score_total")
    quality = score_result.get("quality_score")
    interest = int((company or {}).get("interest_level") or 0)
    high = force or (
        (total is not None and float(total) >= HIGH_PRIORITY_TOTAL)
        or (quality is not None and float(quality) >= HIGH_PRIORITY_QUALITY)
        or interest >= 4
        or (opportunity.get("saved") in (1, True))
        or (opportunity.get("category") or "") in {"community", "entrepreneurial"}
    )
    if not high:
        return {
            "next_action": None,
            "action_rationale": None,
            "why_valuable": None,
            "why_relevant": None,
            "evidence_summary": None,
            "uncertainties": _uncertainties(opportunity, score_result, company),
            "skipped": True,
            "note": "Below high-priority threshold — no action auto-filled.",
        }

    action = choose_action(opportunity, score_result, profile, company)
    assert action in ACTIONS

    breakdown = score_result.get("score_breakdown") or {}
    growth = (breakdown.get("technical_growth") or {}).get("rationale")
    career = (breakdown.get("career_capital") or {}).get("rationale")
    access = (breakdown.get("accessibility") or {}).get("rationale")

    why_valuable = (
        career
        or growth
        or "Potential career capital or learning upside based on available evidence."
    )
    skills = profile.get("skills") if profile else None
    skill_note = ""
    if skills:
        title_desc = f"{opportunity.get('title') or ''} {opportunity.get('description') or ''}".lower()
        hits = [s for s in skills if str(s).lower() in title_desc]
        if hits:
            skill_note = f" Overlaps profile skills: {', '.join(hits[:4])}."
    why_relevant = (
        f"Fits interests / constraints for {((profile or {}).get('name') or 'user')}."
        f"{skill_note} Accessibility: {access or 'n/a'}."
    )

    rationale = (
        f"Recommended '{action}' because score_total={total}, "
        f"quality={quality}, accessibility={score_result.get('accessibility_score')}. "
        "Human must execute — never auto-contact or auto-apply."
    )

    return {
        "next_action": action,
        "action_rationale": rationale,
        "why_valuable": why_valuable,
        "why_relevant": why_relevant,
        "evidence_summary": _evidence_summary(opportunity, score_result),
        "uncertainties": _uncertainties(opportunity, score_result, company),
        "skipped": False,
    }


def apply_action_to_row(
    opportunity: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    """Return opportunity dict with action fields merged (for API responses)."""
    out = dict(opportunity)
    if action.get("skipped"):
        return out
    out["next_action"] = action.get("next_action")
    out["action_rationale"] = action.get("action_rationale")
    out["why_valuable"] = action.get("why_valuable")
    out["why_relevant"] = action.get("why_relevant")
    out["evidence_summary"] = action.get("evidence_summary")
    out["uncertainties_json"] = json.dumps(
        action.get("uncertainties") or [], ensure_ascii=False
    )
    return out
