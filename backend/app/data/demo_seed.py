from app.data.db import connect

ROLES = [
    ("project-manager", "Project Manager", "ICT", "Delivery", "Plans and coordinates delivery across stakeholders, budget, timeline, and risk."),
    ("business-analyst", "Business Analyst", "ICT", "Business Analysis", "Translates business needs into requirements, process models, and solution options."),
    ("data-analyst", "Data Analyst", "ICT", "Data", "Analyses data, builds reports, and communicates insights for business decisions."),
    ("product-manager", "Product Manager", "ICT", "Product", "Defines product strategy, validates user needs, and prioritises delivery."),
    ("ai-engineer", "AI Engineer", "ICT", "AI", "Builds, evaluates, and deploys applied AI systems responsibly."),
]

SKILLS = [
    ("S001", "Project Management", "TSC", 0, 1),
    ("S002", "Stakeholder Management", "CCS", 0, 1),
    ("S003", "Risk Management", "TSC", 0, 0),
    ("S004", "Business Requirements Analysis", "TSC", 0, 1),
    ("S005", "Process Improvement", "TSC", 0, 0),
    ("S006", "Data Analytics", "TSC", 1, 0),
    ("S007", "Data Visualisation", "TSC", 1, 0),
    ("S008", "SQL Querying", "TSC", 0, 0),
    ("S009", "Product Strategy", "TSC", 0, 0),
    ("S010", "User Research", "TSC", 0, 1),
    ("S011", "Machine Learning", "TSC", 1, 0),
    ("S012", "Python Programming", "TSC", 0, 0),
    ("S013", "Communication", "CCS", 0, 1),
    ("S014", "Change Management", "TSC", 0, 1),
]

ROLE_SKILLS = {
    "project-manager": [("S001", 4), ("S002", 4), ("S003", 3), ("S013", 4), ("S014", 3)],
    "business-analyst": [("S004", 4), ("S005", 3), ("S006", 2), ("S002", 5), ("S013", 4)],
    "data-analyst": [("S006", 4), ("S007", 4), ("S008", 3), ("S012", 2), ("S013", 3)],
    "product-manager": [("S009", 4), ("S010", 3), ("S006", 2), ("S002", 4), ("S013", 4)],
    "ai-engineer": [("S011", 4), ("S012", 4), ("S006", 4), ("S008", 3), ("S013", 3)],
}

TASKS = {
    "project-manager": ["Coordinate delivery plans", "Manage delivery risks", "Align stakeholders on scope"],
    "business-analyst": ["Elicit requirements", "Map current and future processes", "Validate solution options"],
    "data-analyst": ["Prepare datasets", "Build dashboards", "Explain trends and drivers"],
    "product-manager": ["Set product outcomes", "Prioritise roadmap", "Validate user needs"],
    "ai-engineer": ["Train models", "Evaluate model performance", "Deploy AI services"],
}


def seed_demo_data() -> dict[str, int]:
    from app.data.db import SCHEMA

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
        conn.executemany("INSERT INTO roles VALUES (?, ?, ?, ?, ?)", ROLES)
        skill_lookup = {code: (title, kind, emerging, casl) for code, title, kind, emerging, casl in SKILLS}
        conn.executemany(
            "INSERT INTO unique_skills VALUES (?, ?, ?, ?, ?, ?)",
            [(code, title, f"Capability in {title.lower()} for Singapore digital roles.", kind, emerging, casl) for code, title, kind, emerging, casl in SKILLS],
        )
        conn.executemany(
            "INSERT INTO tsc_to_unique VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(code, title, None, title, f"Capability in {title.lower()}.", kind, "ICT") for code, title, kind, _, _ in SKILLS],
        )
        rows = []
        ka = []
        for role_id, role_skills in ROLE_SKILLS.items():
            for code, level in role_skills:
                title, kind, _, _ = skill_lookup[code]
                rows.append((role_id, code, title, kind, level))
                ka.append((code, level, f"Level {level}: apply {title.lower()} in role contexts.", f"Concepts and tools for {title}", f"Apply {title} to work outcomes"))
        conn.executemany("INSERT INTO role_skills VALUES (?, ?, ?, ?, ?)", rows)
        task_rows = [(role_id, "Role Delivery", task) for role_id, tasks in TASKS.items() for task in tasks]
        conn.executemany("INSERT INTO role_key_tasks VALUES (?, ?, ?)", task_rows)
        conn.executemany("INSERT INTO skill_ka VALUES (?, ?, ?, ?, ?)", ka)
        conn.execute(
            """
            INSERT INTO unique_skill_role_frequency
            SELECT skill_title, COUNT(DISTINCT role_id)
            FROM role_skills
            GROUP BY skill_title
            """
        )
        conn.commit()
        return {
            "roles": len(ROLES),
            "role_skills": len(rows),
            "unique_skills": len(SKILLS),
            "skill_mappings": len(SKILLS),
        }
