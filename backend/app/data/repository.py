from app.data.db import connect
from app.models.schemas import NormalizedSkill, Role
from app.services.normalize import normalize_role_skill


def list_roles(q: str | None = None, sector: str | None = None, track: str | None = None) -> list[Role]:
    sql = "SELECT * FROM roles WHERE 1=1"
    params: list[str] = []
    if q:
        sql += " AND lower(role_title) LIKE ?"
        params.append(f"%{q.lower()}%")
    if sector:
        sql += " AND sector = ?"
        params.append(sector)
    if track:
        sql += " AND track = ?"
        params.append(track)
    sql += " ORDER BY role_title"
    with connect() as conn:
        return [Role(**dict(row)) for row in conn.execute(sql, params)]


def get_role(role_id: str) -> Role:
    with connect() as conn:
        row = conn.execute("SELECT * FROM roles WHERE role_id = ?", (role_id,)).fetchone()
        if row is None:
            raise KeyError(role_id)
        return Role(**dict(row))


def get_role_skills(role_id: str) -> list[NormalizedSkill]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              rs.skill_code,
              rs.skill_title AS raw_title,
              COALESCE(m.unique_skill_title, rs.skill_title) AS canonical_title,
              COALESCE(m.unique_skill_type, rs.skill_type) AS skill_type,
              rs.proficiency_level,
              COALESCE(us.is_emerging, 0) AS is_emerging,
              COALESCE(us.is_casl, 0) AS is_casl,
              CASE WHEN m.unique_skill_title IS NULL THEN 0 ELSE 1 END AS mapped
            FROM role_skills rs
            LEFT JOIN tsc_to_unique m
              ON rs.skill_code = m.skill_code
            LEFT JOIN unique_skills us
              ON lower(us.skill_title) = lower(COALESCE(m.unique_skill_title, rs.skill_title))
            WHERE rs.role_id = ?
            """,
            (role_id,),
        ).fetchall()
        if rows:
            return [_skill_from_row(row) for row in rows]
        fallback = conn.execute("SELECT * FROM role_skills WHERE role_id = ?", (role_id,)).fetchall()
        return [normalize_role_skill(dict(row), conn) for row in fallback]


def get_all_role_skills_index() -> dict[str, list[NormalizedSkill]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              rs.role_id,
              rs.skill_code,
              rs.skill_title AS raw_title,
              COALESCE(m.unique_skill_title, rs.skill_title) AS canonical_title,
              COALESCE(m.unique_skill_type, rs.skill_type) AS skill_type,
              rs.proficiency_level,
              COALESCE(us.is_emerging, 0) AS is_emerging,
              COALESCE(us.is_casl, 0) AS is_casl,
              CASE WHEN m.unique_skill_title IS NULL THEN 0 ELSE 1 END AS mapped
            FROM role_skills rs
            LEFT JOIN tsc_to_unique m
              ON rs.skill_code = m.skill_code
            LEFT JOIN unique_skills us
              ON lower(us.skill_title) = lower(COALESCE(m.unique_skill_title, rs.skill_title))
            """
        ).fetchall()
    index: dict[str, list[NormalizedSkill]] = {}
    for row in rows:
        index.setdefault(row["role_id"], []).append(_skill_from_row(row))
    return index


def list_unique_skills(limit: int = 200) -> list[NormalizedSkill]:
    """The catalogue of unique SkillsFuture skills (TSC/CCS), ordered by how many
    roles reference them, so AI skill inference can be grounded in real skills."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              us.skill_title AS canonical_title,
              us.skill_type,
              COALESCE(us.is_emerging, 0) AS is_emerging,
              COALESCE(us.is_casl, 0) AS is_casl,
              COALESCE(f.role_count, 0) AS role_count
            FROM unique_skills us
            LEFT JOIN unique_skill_role_frequency f
              ON lower(f.unique_skill_title) = lower(us.skill_title)
            ORDER BY role_count DESC, us.skill_title
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    skills: list[NormalizedSkill] = []
    for row in rows:
        kind = str(row["skill_type"] or "TSC").upper()
        skills.append(
            NormalizedSkill(
                raw_title=row["canonical_title"],
                canonical_title=row["canonical_title"],
                skill_type="CCS" if kind == "CCS" else "TSC",
                is_emerging=bool(row["is_emerging"]),
                is_casl=bool(row["is_casl"]),
                mapped=True,
            )
        )
    return skills


def get_key_tasks(role_id: str) -> list[dict[str, str]]:
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT critical_work_function, key_task FROM role_key_tasks WHERE role_id = ?", (role_id,))]


def role_frequency(title: str) -> int:
    with connect() as conn:
        row = conn.execute("SELECT role_count FROM unique_skill_role_frequency WHERE lower(unique_skill_title) = ?", (title.lower(),)).fetchone()
        return int(row["role_count"]) if row else 0


def _skill_from_row(row) -> NormalizedSkill:
    kind = str(row["skill_type"] or "TSC").upper()
    return NormalizedSkill(
        skill_code=row["skill_code"],
        raw_title=row["raw_title"],
        canonical_title=row["canonical_title"],
        skill_type="CCS" if kind == "CCS" else "TSC",
        proficiency_level=row["proficiency_level"],
        is_emerging=bool(row["is_emerging"]),
        is_casl=bool(row["is_casl"]),
        mapped=bool(row["mapped"]),
    )
