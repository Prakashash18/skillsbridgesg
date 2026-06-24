import statistics

from app.data.repository import get_key_tasks, get_role, get_role_skills, role_frequency
from app.llm.client import LLMClient
from app.models.schemas import GapAnalysisResponse, GapSkill, NormalizedSkill, PracticalGapSkill, ProfileResponse
from app.services.normalize import comparison_key
from app.utils.scoring import PARTIAL_PROF_CREDIT, skill_weight


def analyse_gap(profile: ProfileResponse, target_role_id: str, market_frequency: dict[str, int] | None = None) -> GapAnalysisResponse:
    target_role = get_role(target_role_id)
    target_skills = get_role_skills(target_role_id)
    client = LLMClient()
    if client.available:
        ai_gap = _analyse_gap_with_ai(profile, target_role, target_skills, market_frequency, client)
        if ai_gap:
            return ai_gap
    return _fallback_gap(profile, target_role, target_skills, market_frequency, key_present=client.available)


def _analyse_gap_with_ai(profile: ProfileResponse, target_role, target_skills: list[NormalizedSkill], market_frequency: dict[str, int] | None, client: LLMClient) -> GapAnalysisResponse | None:
    result = client.json_response(
        instructions=(
            "You are SkillBridge SG's practical gap analyst. Compare the user's natural current profile with the target SkillsFuture role, "
            "catalog snippets, key tasks, and any market signals. Do not just perform exact skill matching. "
            "Identify practical skills the user must prove for this role. Return strict JSON with ai_summary, match_score 0-1, "
            "weighted_overlap 0-1, matched_skills, proficiency_gap_skills, and practical_gap_skills. "
            "Each practical_gap_skill must include skill, why_required, current_signal, and evidence_source "
            "(conversation, catalog, or jobs). Prefer concrete skills such as Python lab facilitation, IoT assessment rubrics, SQL querying, stakeholder workshops."
        ),
        payload={
            "current_profile": {
                "mapped_role": profile.role.model_dump(),
                "narrative_summary": profile.narrative_summary,
                "evidence_summary": profile.evidence_summary,
                "current_skills": [skill.canonical_title for skill in profile.skills[:16]],
            },
            "target_role": target_role.model_dump(),
            "target_catalog_skills": [
                {
                    "title": skill.canonical_title,
                    "type": skill.skill_type,
                    "proficiency_level": skill.proficiency_level,
                }
                for skill in target_skills[:18]
            ],
            "target_key_tasks": get_key_tasks(target_role.role_id)[:12],
            "market_frequency": market_frequency or {},
        },
    )
    if not result:
        return None

    practical_gaps = _practical_gaps(result.get("practical_gap_skills", []))
    missing = [_gap_from_practical(item, "Missing") for item in practical_gaps]
    prof_gap_names = {comparison_key(str(item)) for item in result.get("proficiency_gap_skills", []) if str(item).strip()}
    prof_gaps = [
        _gap_from_practical(item, "Proficiency Gap")
        for item in practical_gaps
        if comparison_key(item.skill) in prof_gap_names
    ]
    if prof_gaps:
        missing = [item for item in missing if comparison_key(item.skill.canonical_title) not in prof_gap_names]
    matched = [
        GapSkill(skill=NormalizedSkill(raw_title=skill, canonical_title=skill, skill_type="TSC", mapped=False), status="Matched")
        for skill in [str(item).strip() for item in result.get("matched_skills", []) if str(item).strip()]
    ]
    if not missing and not prof_gaps:
        missing = _fallback_missing(profile, target_skills, limit=4)

    match_score = _bounded_float(result.get("match_score"), default=0.55)
    weighted_overlap = _bounded_float(result.get("weighted_overlap"), default=match_score)
    return GapAnalysisResponse(
        current_role=profile.role,
        target_role=target_role,
        profile_source=profile.profile_source,
        match_score=round(match_score, 4),
        weighted_overlap=round(weighted_overlap, 4),
        matched=matched,
        proficiency_gaps=prof_gaps,
        missing=missing,
        transferable=transferable_skills(profile.skills),
        analysis_mode="openai_catalog",
        ai_summary=str(result.get("ai_summary") or "").strip() or None,
        practical_gap_skills=practical_gaps,
    )


def _fallback_gap(profile: ProfileResponse, target_role, target_skills: list[NormalizedSkill], market_frequency: dict[str, int] | None = None, key_present: bool = False) -> GapAnalysisResponse:
    current_by_key = {comparison_key(skill.canonical_title): skill for skill in profile.skills}
    matched: list[GapSkill] = []
    prof_gaps: list[GapSkill] = []
    missing: list[GapSkill] = []
    for target in target_skills:
        key = comparison_key(target.canonical_title)
        current = current_by_key.get(key)
        target_level = target.proficiency_level or 0
        if current:
            current_level = current.proficiency_level or 0
            if current_level >= target_level:
                matched.append(GapSkill(skill=target, current_proficiency_level=current_level, target_proficiency_level=target_level, status="Matched"))
            else:
                prof_gaps.append(GapSkill(skill=target, current_proficiency_level=current_level, target_proficiency_level=target_level, gap=target_level - current_level, priority=_priority(target, market_frequency), status="Proficiency Gap"))
        else:
            missing.append(GapSkill(skill=target, target_proficiency_level=target_level, gap=target_level, priority=_priority(target, market_frequency), status="Missing"))
    missing.sort(key=lambda item: item.priority, reverse=True)
    prof_gaps.sort(key=lambda item: item.priority, reverse=True)
    match_score = len(matched) / len(target_skills) if target_skills else 0
    weighted_overlap = _weighted_overlap(matched, prof_gaps, target_skills)
    return GapAnalysisResponse(
        current_role=profile.role,
        target_role=target_role,
        profile_source=profile.profile_source,
        match_score=round(match_score, 4),
        weighted_overlap=round(weighted_overlap, 4),
        matched=matched,
        proficiency_gaps=prof_gaps,
        missing=missing,
        transferable=transferable_skills(profile.skills),
        analysis_mode="mock_fallback",
        ai_summary=(
            "AI gap reasoning is temporarily unavailable, so this analysis uses the selected SkillsFuture role profile and catalog skills."
            if key_present
            else "Demo mode: gap analysis uses the selected SkillsFuture role profile. Add OPENAI_API_KEY for practical AI gap reasoning."
        ),
        practical_gap_skills=[
            PracticalGapSkill(
                skill=item.skill.canonical_title,
                why_required=f"{item.skill.canonical_title} appears in the SkillsFuture role profile for {target_role.role_title}.",
                current_signal="Not clearly evidenced yet in the conversation.",
                evidence_source="catalog",
            )
            for item in (missing[:4] + prof_gaps[:3])
        ],
    )


def _weighted_overlap(matched: list[GapSkill], prof_gaps: list[GapSkill], target_skills: list[NormalizedSkill]) -> float:
    denominator = sum(skill_weight(skill.skill_type) for skill in target_skills)
    if denominator == 0:
        return 0
    numerator = sum(skill_weight(item.skill.skill_type) for item in matched)
    numerator += PARTIAL_PROF_CREDIT * sum(skill_weight(item.skill.skill_type) for item in prof_gaps)
    return numerator / denominator


def _fallback_missing(profile: ProfileResponse, target_skills: list[NormalizedSkill], limit: int) -> list[GapSkill]:
    current = {comparison_key(skill.canonical_title) for skill in profile.skills}
    missing = []
    for skill in target_skills:
        if comparison_key(skill.canonical_title) not in current:
            missing.append(GapSkill(skill=skill, target_proficiency_level=skill.proficiency_level or 0, gap=skill.proficiency_level or 0, status="Missing"))
    return missing[:limit]


def _gap_from_practical(item: PracticalGapSkill, status: str) -> GapSkill:
    return GapSkill(
        skill=NormalizedSkill(raw_title=item.skill, canonical_title=item.skill, skill_type="TSC", mapped=False),
        target_proficiency_level=3,
        gap=3,
        priority=3,
        status=status,
    )


def _practical_gaps(raw_items) -> list[PracticalGapSkill]:
    if not isinstance(raw_items, list):
        return []
    gaps: list[PracticalGapSkill] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill") or "").strip()
        if not skill:
            continue
        source = item.get("evidence_source") if item.get("evidence_source") in {"conversation", "catalog", "jobs"} else "catalog"
        gaps.append(
            PracticalGapSkill(
                skill=skill,
                why_required=str(item.get("why_required") or "Required for the target role.").strip(),
                current_signal=str(item.get("current_signal") or "").strip() or None,
                evidence_source=source,
            )
        )
    return gaps


def _bounded_float(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _priority(skill: NormalizedSkill, market_frequency: dict[str, int] | None = None) -> float:
    freq = role_frequency(skill.canonical_title)
    all_freq = [role_frequency(skill.canonical_title), 1]
    related_bonus = freq / max(all_freq)
    market_count = (market_frequency or {}).get(skill.canonical_title, 0)
    max_market = max((market_frequency or {"": 0}).values()) or 1
    market_bonus = market_count / max_market
    return (
        (skill.proficiency_level or 0)
        + (2 if skill.is_emerging else 0)
        + (1 if skill.is_casl else 0)
        + (1 if skill.skill_type == "TSC" else 0)
        + related_bonus
        + market_bonus
    )


def transferable_skills(current_skills: list[NormalizedSkill], top_n: int = 5) -> list[NormalizedSkill]:
    counts = [(skill, role_frequency(skill.canonical_title)) for skill in current_skills]
    positive = [count for _, count in counts if count > 0]
    threshold = statistics.quantiles(positive, n=4)[2] if len(positive) >= 4 else 1
    ranked = sorted(((skill, count) for skill, count in counts if count >= threshold), key=lambda item: item[1], reverse=True)
    return [skill for skill, _ in ranked[:top_n]]
