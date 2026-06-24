from pathlib import Path
import re

import pandas as pd

from app.data.demo_seed import seed_demo_data
from app.data.db import SCHEMA, connect

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EXPECTED = [
    "jobsandskills-skillsfuture-skills-framework-dataset.xlsx",
    "jobsandskills-skillsfuture-tsc-to-unique-skills-mapping.xlsx",
    "jobsandskills-skillsfuture-unique-skills-list.xlsx",
]


def inspect_workbooks() -> list[dict]:
    reports = []
    for filename in EXPECTED:
        path = DATA_DIR / filename
        if not path.exists():
            reports.append({"file": filename, "status": "missing"})
            continue
        workbook = pd.ExcelFile(path)
        sheets = []
        for sheet in workbook.sheet_names:
            preview = workbook.parse(sheet, nrows=3)
            sheets.append({"sheet": sheet, "headers": list(preview.columns), "rows": preview.fillna("").to_dict(orient="records")})
        reports.append({"file": filename, "status": "inspected", "sheets": sheets})
    return reports


def run_ingest() -> dict:
    reports = inspect_workbooks()
    if any(report["status"] == "missing" for report in reports):
        counts = seed_demo_data()
        return {"mode": "demo_seed", "counts": counts, "inspection": reports}
    counts = ingest_workbooks()
    return {"mode": "skillsfuture_workbooks", "counts": counts, "inspection": reports}


def ingest_workbooks() -> dict[str, int]:
    framework = DATA_DIR / "jobsandskills-skillsfuture-skills-framework-dataset.xlsx"
    mapping = DATA_DIR / "jobsandskills-skillsfuture-tsc-to-unique-skills-mapping.xlsx"
    unique = DATA_DIR / "jobsandskills-skillsfuture-unique-skills-list.xlsx"

    role_desc = pd.read_excel(framework, sheet_name="Job Role_Description").fillna("")
    role_tasks = pd.read_excel(framework, sheet_name="Job Role_CWF_KT").fillna("")
    role_skills = pd.read_excel(framework, sheet_name="Job Role_TCS_CCS").fillna("")
    ka_rows = pd.read_excel(framework, sheet_name="TSC_CCS_K&A").fillna("")
    mapping_rows = pd.read_excel(mapping, sheet_name="data").fillna("")
    unique_rows = pd.read_excel(unique, sheet_name="Unique Skills List").fillna("")

    role_ids = {
        _role_key(row["Sector"], row["Track"], row["Job Role"]): _make_role_id(row["Sector"], row["Track"], row["Job Role"])
        for _, row in role_desc.iterrows()
    }

    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.executescript(
            """
            DELETE FROM roles;
            DELETE FROM role_key_tasks;
            DELETE FROM role_skills;
            DELETE FROM unique_skills;
            DELETE FROM tsc_to_unique;
            DELETE FROM skill_ka;
            DELETE FROM unique_skill_role_frequency;
            """
        )
        role_records = []
        seen_roles = set()
        for _, row in role_desc.iterrows():
            role_id = role_ids[_role_key(row["Sector"], row["Track"], row["Job Role"])]
            if role_id in seen_roles:
                continue
            seen_roles.add(role_id)
            role_records.append((role_id, row["Job Role"], row["Sector"], row["Track"], row["Job Role Description"]))
        conn.executemany("INSERT INTO roles VALUES (?, ?, ?, ?, ?)", role_records)

        task_records = []
        for _, row in role_tasks.iterrows():
            role_id = role_ids.get(_role_key(row["Sector"], row["Track"], row["Job Role"]))
            if role_id:
                task_records.append((role_id, row["Critical Work Function"], row["Key Tasks"]))
        conn.executemany("INSERT INTO role_key_tasks VALUES (?, ?, ?)", task_records)

        skill_records = []
        for _, row in role_skills.iterrows():
            role_id = role_ids.get(_role_key(row["Sector"], row["Track"], row["Job Role"]))
            if role_id:
                skill_records.append(
                    (
                        role_id,
                        _str_or_none(row["TSC_CCS Code"]),
                        row["TSC_CCS Title"],
                        _skill_type(row["TSC_CCS Type"]),
                        _int_or_none(row["Proficiency Level"]),
                    )
                )
        conn.executemany("INSERT INTO role_skills VALUES (?, ?, ?, ?, ?)", skill_records)

        unique_records = []
        for index, row in unique_rows.iterrows():
            title = str(row["skill_title"]).strip()
            if not title:
                continue
            unique_records.append(
                (
                    f"unique-{index + 1}",
                    title,
                    row["skill_description"],
                    _skill_type(row["skill_type"]),
                    _bool(row["Emerging Skills"]),
                    _bool(row["CASL Skills"]),
                )
            )
        conn.executemany("INSERT INTO unique_skills VALUES (?, ?, ?, ?, ?, ?)", unique_records)

        mapping_records = []
        for _, row in mapping_rows.iterrows():
            mapping_records.append(
                (
                    _str_or_none(row["skills_framework_skill_code"]),
                    row["skills_framework_skill_title"],
                    _int_or_none(row["skills_framework_skill_pl"]),
                    row["Unique skill_updated_skill_title"],
                    row["Unique skill_updated_skill_desc"],
                    _skill_type(row["Unique skill_updated_skill_type"]),
                    row["Unique skill_updated_sector_tagging"],
                )
            )
        conn.executemany("INSERT INTO tsc_to_unique VALUES (?, ?, ?, ?, ?, ?, ?)", mapping_records)

        grouped_ka = (
            ka_rows.groupby(["TSC_CCS Code", "Proficiency Level", "Proficiency Description", "Knowledge / Ability Classification"])["Knowledge / Ability Items"]
            .apply(lambda values: " | ".join(str(value) for value in values if str(value).strip()))
            .reset_index()
        )
        ka_lookup: dict[tuple[str, int, str], dict[str, str]] = {}
        for _, row in grouped_ka.iterrows():
            key = (row["TSC_CCS Code"], _int_or_none(row["Proficiency Level"]) or 0, row["Proficiency Description"])
            bucket = ka_lookup.setdefault(key, {"knowledge": "", "ability": ""})
            classification = str(row["Knowledge / Ability Classification"]).lower()
            if "knowledge" in classification:
                bucket["knowledge"] = row["Knowledge / Ability Items"]
            else:
                bucket["ability"] = row["Knowledge / Ability Items"]
        ka_records = [(code, level, desc, items["knowledge"], items["ability"]) for (code, level, desc), items in ka_lookup.items()]
        conn.executemany("INSERT INTO skill_ka VALUES (?, ?, ?, ?, ?)", ka_records)

        conn.execute(
            """
            INSERT INTO unique_skill_role_frequency
            SELECT canonical, COUNT(DISTINCT role_id)
            FROM (
              SELECT rs.role_id, COALESCE(m.unique_skill_title, rs.skill_title) AS canonical
              FROM role_skills rs
              LEFT JOIN tsc_to_unique m
                ON rs.skill_code = m.skill_code
            )
            GROUP BY canonical
            """
        )
        conn.commit()

    return {
        "roles": len(role_records),
        "role_skills": len(skill_records),
        "unique_skills": len(unique_records),
        "skill_mappings": len(mapping_records),
    }


def _role_key(sector: object, track: object, role: object) -> str:
    return f"{sector}|{track}|{role}"


def _make_role_id(sector: object, track: object, role: object) -> str:
    value = f"{sector}-{track}-{role}".lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:180]


def _skill_type(value: object) -> str:
    return "CCS" if str(value).strip().upper() == "CCS" else "TSC"


def _int_or_none(value: object) -> int | None:
    try:
        if value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: object) -> str | None:
    text = str(value).strip()
    return text or None


def _bool(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    return 1 if str(value).strip().lower() in {"true", "1", "yes", "y"} else 0
