import sqlite3

from rapidfuzz import fuzz, process

from app.models.schemas import NormalizedSkill


def comparison_key(title: str) -> str:
    return title.strip().lower()


def _unique_flags(conn: sqlite3.Connection, title: str) -> tuple[bool, bool]:
    row = conn.execute(
        "SELECT is_emerging, is_casl FROM unique_skills WHERE lower(skill_title) = ?",
        (comparison_key(title),),
    ).fetchone()
    return (bool(row["is_emerging"]), bool(row["is_casl"])) if row else (False, False)


def normalize_role_skill(row: dict, conn: sqlite3.Connection) -> NormalizedSkill:
    skill_code = row.get("skill_code")
    raw_title = row.get("skill_title") or row.get("raw_title") or ""
    match = None
    if skill_code:
        match = conn.execute("SELECT * FROM tsc_to_unique WHERE skill_code = ? LIMIT 1", (skill_code,)).fetchone()
    if match is None:
        match = conn.execute("SELECT * FROM tsc_to_unique WHERE skill_title = ? LIMIT 1", (raw_title,)).fetchone()
    if match is None:
        match = conn.execute("SELECT * FROM tsc_to_unique WHERE lower(skill_title) = ? LIMIT 1", (comparison_key(raw_title),)).fetchone()
    if match is None:
        candidates = conn.execute("SELECT skill_title FROM tsc_to_unique").fetchall()
        titles = [candidate["skill_title"] for candidate in candidates]
        best = process.extractOne(raw_title, titles, scorer=fuzz.token_sort_ratio) if titles else None
        if best and best[1] >= 90:
            match = conn.execute("SELECT * FROM tsc_to_unique WHERE skill_title = ? LIMIT 1", (best[0],)).fetchone()

    canonical = match["unique_skill_title"] if match else raw_title
    skill_type = (match["unique_skill_type"] if match else row.get("skill_type")) or "TSC"
    is_emerging, is_casl = _unique_flags(conn, canonical)
    return NormalizedSkill(
        skill_code=skill_code,
        raw_title=raw_title,
        canonical_title=canonical,
        skill_type=skill_type if skill_type in {"TSC", "CCS"} else "TSC",
        proficiency_level=row.get("proficiency_level"),
        is_emerging=is_emerging,
        is_casl=is_casl,
        mapped=match is not None,
    )

