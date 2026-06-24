TSC_WEIGHT = 1.0
CCS_WEIGHT = 0.3
PARTIAL_PROF_CREDIT = 0.5


def skill_weight(skill_type: str | None) -> float:
    return TSC_WEIGHT if skill_type == "TSC" else CCS_WEIGHT

