"""Editable user profile (JSON in DB + data/profile.json fallback)."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_RANKING_WEIGHTS: dict[str, float] = {
    "technical_growth": 1.2,
    "engineering_culture": 1.1,
    "peer_quality": 1.1,
    "compensation": 1.0,
    "accessibility": 1.0,
    "career_capital": 1.2,
    "industry_growth": 1.0,
    "autonomy": 1.0,
    "lifestyle": 0.9,
    "optionality": 1.1,
    "entrepreneurial_upside": 1.0,
    "evidence_strength": 1.3,
}

DEFAULT_PROFILE: dict[str, Any] = {
    "name": "Jason Xavier",
    "location": "Auckland, New Zealand",
    "citizenship": ["NZ"],
    "education": [
        {
            "degree": "BE(Hons) Software Engineering",
            "institution": "University of Auckland",
        }
    ],
    "years_experience": 1.5,
    "skills": [
        "C#",
        ".NET",
        "JavaScript",
        "full-stack",
        "mobile",
        "Web3",
        "DeFi",
    ],
    "interests": [
        "exceptional engineering teams",
        "technically demanding environments",
        "entrepreneurship",
        "emerging industries",
        "remote work",
        "mentorship",
        "autonomy",
        "compensation",
        "technical growth",
        "optionality",
    ],
    "willing_to_relocate": True,
    "risk_tolerance": "calculated",
    "ranking_weights": dict(DEFAULT_RANKING_WEIGHTS),
    # Blend used by scoring.score_total (quality / accessibility).
    "score_blend": {"quality": 0.7, "accessibility": 0.3},
}

# Dimensions that feed quality_score (accessibility scored separately).
QUALITY_DIMENSIONS: tuple[str, ...] = tuple(
    k for k in DEFAULT_RANKING_WEIGHTS if k != "accessibility"
)

PROFILE_FILE_DEFAULT = Path("data/profile.json")


def normalize_profile(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Merge partial profile dict onto defaults; ensure ranking_weights complete."""
    profile = deepcopy(DEFAULT_PROFILE)
    if not raw:
        return profile
    for key, value in raw.items():
        if key == "ranking_weights" and isinstance(value, dict):
            weights = dict(DEFAULT_RANKING_WEIGHTS)
            for wk, wv in value.items():
                try:
                    weights[str(wk)] = float(wv)
                except (TypeError, ValueError):
                    continue
            profile["ranking_weights"] = weights
        elif key == "score_blend" and isinstance(value, dict):
            blend = dict(profile["score_blend"])
            for bk, bv in value.items():
                try:
                    blend[str(bk)] = float(bv)
                except (TypeError, ValueError):
                    continue
            profile["score_blend"] = blend
        else:
            profile[key] = value
    return profile


def profile_to_api(profile: dict[str, Any]) -> dict[str, Any]:
    """API-friendly copy (JSON-serializable)."""
    return json.loads(json.dumps(normalize_profile(profile)))


def get_ranking_weights(profile: dict[str, Any] | None = None) -> dict[str, float]:
    p = normalize_profile(profile)
    return {k: float(v) for k, v in p["ranking_weights"].items()}


def set_ranking_weight(
    profile: dict[str, Any], dimension: str, weight: float
) -> dict[str, Any]:
    """Return a new profile with one ranking weight updated."""
    out = normalize_profile(profile)
    out["ranking_weights"][dimension] = float(weight)
    return out


def load_profile_from_file(path: Path | str | None = None) -> dict[str, Any]:
    path = Path(path) if path else PROFILE_FILE_DEFAULT
    if not path.exists():
        return normalize_profile(None)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return normalize_profile(None)
    return normalize_profile(data)


def save_profile_to_file(
    profile: dict[str, Any], path: Path | str | None = None
) -> Path:
    path = Path(path) if path else PROFILE_FILE_DEFAULT
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_profile(profile)
    with path.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def _ensure_profile_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data_json TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    # Older Agent A stub omitted updated_at — add if missing.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(profile)").fetchall()}
    if "updated_at" not in cols:
        try:
            conn.execute("ALTER TABLE profile ADD COLUMN updated_at TEXT")
        except sqlite3.Error:
            pass


def load_profile(
    conn: sqlite3.Connection | None = None,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Load profile from DB row (preferred) then file, else defaults."""
    if conn is not None:
        _ensure_profile_table(conn)
        row = conn.execute(
            "SELECT data_json FROM profile WHERE id = 1"
        ).fetchone()
        if row and row[0]:
            try:
                data = json.loads(row[0])
                if isinstance(data, dict):
                    return normalize_profile(data)
            except json.JSONDecodeError:
                pass

    file_path = Path(path) if path else PROFILE_FILE_DEFAULT
    if file_path.exists():
        return load_profile_from_file(file_path)
    return normalize_profile(None)


def save_profile(
    profile: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    *,
    path: Path | str | None = None,
    also_file: bool = True,
) -> dict[str, Any]:
    """Persist profile to DB and optionally data/profile.json."""
    from datetime import datetime, timezone

    normalized = normalize_profile(profile)
    payload = json.dumps(normalized, ensure_ascii=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if conn is not None:
        _ensure_profile_table(conn)
        conn.execute(
            """
            INSERT INTO profile (id, data_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (payload, now),
        )
        conn.commit()

    if also_file:
        save_profile_to_file(normalized, path)

    return normalized
