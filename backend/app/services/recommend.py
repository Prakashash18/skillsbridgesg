from app.data.repository import get_role_skills, list_roles
from app.llm.client import LLMClient
from app.models.schemas import NormalizedSkill, PracticalGapSkill, ProfileResponse, RecommendResponse, RecommendedRole, Role
from app.services.normalize import comparison_key

TIER_NOTES = {
    "Adjacent": "Strong overlap. Mostly proficiency lifts and 1-2 new skills.",
    "Stretch": "Reachable with focused effort. Several real gaps to close.",
    "Pivot": "A significant change. Expect months, not weeks; this plan starts you off.",
}


def recommend_roles(profile: ProfileResponse, top_k: int = 5) -> RecommendResponse:
    candidates = _candidate_roles(profile, max(top_k * 6, 24))
    client = LLMClient()
    if client.available:
        ai_recommendations = _recommend_with_ai(profile, candidates, top_k, client)
        if ai_recommendations:
            return RecommendResponse(profile_source=profile.profile_source, recommendations=ai_recommendations)
    return RecommendResponse(
        profile_source=profile.profile_source,
        recommendations=_fallback_recommendations(profile, candidates, top_k, key_present=client.available),
    )


def _recommend_with_ai(profile: ProfileResponse, candidates: list[Role], top_k: int, client: LLMClient) -> list[RecommendedRole]:
    role_by_id = {role.role_id: role for role in candidates}
    result = client.json_response(
        instructions=(
            "You are SkillBridge SG's role exploration engine. Recommend same-domain and cross-domain roles using the user's natural profile, "
            "candidate SkillsFuture roles, and small catalog skill snippets. Do not do deterministic skill overlap scoring. "
            "Focus on realistic career fit, practical skill gaps, and why the role makes sense. "
            "Return strict JSON with key recommendations: an array of objects with role_id, match_score 0-1, tier "
            "(Adjacent, Stretch, or Pivot), domain_type (same_domain or cross_domain), ai_rationale, required_skills, "
            "and practical_gap_skills. Each practical_gap_skill must include skill, why_required, current_signal, and evidence_source "
            "(conversation, catalog, or jobs). Return at most the requested same-domain and cross-domain roles."
        ),
        payload={
            "current_profile": _profile_context(profile),
            "requested_per_group": top_k,
            "candidate_roles": [_catalog_snippet(role, profile) for role in candidates],
        },
    )
    if not result:
        return []
    items = result.get("recommendations", [])
    if not isinstance(items, list):
        return []

    recommendations: list[RecommendedRole] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        role_id = str(item.get("role_id") or "").strip()
        role = role_by_id.get(role_id)
        if not role or role.role_id in seen:
            continue
        seen.add(role.role_id)
        domain_type = item.get("domain_type") if item.get("domain_type") in {"same_domain", "cross_domain"} else _domain_type(profile, role)
        tier = item.get("tier") if item.get("tier") in TIER_NOTES else _tier(float(item.get("match_score") or 0))
        practical_gaps = _practical_gaps(item.get("practical_gap_skills", []), default_source="catalog")
        required_skills = [str(skill).strip() for skill in item.get("required_skills", []) if str(skill).strip()][:8]
        top_missing = _skills_from_practical_gaps(practical_gaps) or _fallback_missing_skills(profile, role, limit=3)
        match_score = max(0.0, min(1.0, float(item.get("match_score") or 0.55)))
        recommendations.append(
            RecommendedRole(
                role=role,
                role_fit_score=round(match_score, 4),
                match_score=round(match_score, 4),
                weighted_overlap=round(match_score, 4),
                tier=tier,
                tier_note=TIER_NOTES[tier],
                domain_type=domain_type,
                top_missing_skills=top_missing[:3],
                ai_rationale=str(item.get("ai_rationale") or "").strip() or None,
                required_skills=required_skills,
                practical_gap_skills=practical_gaps[:5],
            )
        )
    return _balanced(recommendations, top_k)


def _fallback_recommendations(profile: ProfileResponse, candidates: list[Role], top_k: int, key_present: bool = False) -> list[RecommendedRole]:
    rationale = (
        "AI role-fit reasoning is temporarily unavailable, so this ranking comes from the SkillsFuture role profile and catalog overlap."
        if key_present
        else "Demo mode: ranked from role metadata and catalog overlap. Add OPENAI_API_KEY for natural-language role-fit reasoning."
    )
    recommendations: list[RecommendedRole] = []
    for rank, role in enumerate(candidates):
        match_score = max(0.35, 0.82 - rank * 0.035)
        tier = _tier(match_score)
        domain_type = _domain_type(profile, role)
        missing = _fallback_missing_skills(profile, role, limit=3)
        practical_gaps = [
            PracticalGapSkill(
                skill=skill.canonical_title,
                why_required=f"{skill.canonical_title} appears in the SkillsFuture role profile for {role.role_title}.",
                current_signal="Not clearly evidenced yet in the conversation.",
                evidence_source="catalog",
            )
            for skill in missing[:3]
        ]
        recommendations.append(
            RecommendedRole(
                role=role,
                role_fit_score=round(match_score, 4),
                match_score=round(match_score, 4),
                weighted_overlap=round(match_score, 4),
                tier=tier,
                tier_note=TIER_NOTES[tier],
                domain_type=domain_type,
                top_missing_skills=missing,
                ai_rationale=rationale,
                required_skills=[skill.canonical_title for skill in get_role_skills(role.role_id)[:6]],
                practical_gap_skills=practical_gaps,
            )
        )
    return _balanced(recommendations, top_k)


def _candidate_roles(profile: ProfileResponse, limit: int) -> list[Role]:
    roles = [role for role in list_roles() if role.role_id != profile.role.role_id]
    scored = [(_candidate_score(profile, role), role) for role in roles]
    scored.sort(key=lambda item: item[0], reverse=True)
    same = [role for score, role in scored if role.sector == profile.role.sector and score >= 0]
    cross = [role for score, role in scored if role.sector != profile.role.sector and score >= 0]
    combined = same[: limit // 2] + cross[: limit // 2]
    if len(combined) < limit:
        existing = {role.role_id for role in combined}
        combined.extend(role for _, role in scored if role.role_id not in existing)
    return combined[:limit]


def _candidate_score(profile: ProfileResponse, role: Role) -> float:
    profile_text = _profile_search_text(profile)
    role_text = " ".join([role.role_title, role.sector or "", role.track or "", role.description or ""]).lower()
    score = 0.0
    if role.sector == profile.role.sector:
        score += 12
    if role.track == profile.role.track:
        score += 4
    for token in profile_text.split():
        if len(token) > 3 and token in role_text:
            score += 1.5
    if "education" in profile_text or "lecturer" in profile_text or "teach" in profile_text:
        if any(term in role_text for term in ["learning", "education", "trainer", "facilitator", "courseware", "curriculum"]):
            score += 8
    if "iot" in profile_text or "python" in profile_text or "programming" in profile_text:
        if any(term in role_text for term in ["technology", "software", "learning technology", "digital", "infocomm"]):
            score += 5
    return score


def _catalog_snippet(role: Role, profile: ProfileResponse) -> dict:
    skills = get_role_skills(role.role_id)[:10]
    return {
        **role.model_dump(),
        "domain_type": _domain_type(profile, role),
        "catalog_skills": [
            {
                "title": skill.canonical_title,
                "type": skill.skill_type,
                "proficiency_level": skill.proficiency_level,
            }
            for skill in skills
        ],
    }


def _profile_context(profile: ProfileResponse) -> dict:
    return {
        "mapped_role": profile.role.model_dump(),
        "narrative_summary": profile.narrative_summary,
        "evidence_summary": profile.evidence_summary,
        "current_skills": [skill.canonical_title for skill in profile.skills[:12]],
    }


def _profile_search_text(profile: ProfileResponse) -> str:
    parts = [
        profile.role.role_title,
        profile.role.sector or "",
        profile.role.track or "",
        profile.narrative_summary or "",
        " ".join(profile.evidence_summary),
        " ".join(skill.canonical_title for skill in profile.skills[:12]),
    ]
    return comparison_key(" ".join(parts))


def _fallback_missing_skills(profile: ProfileResponse, role: Role, limit: int) -> list[NormalizedSkill]:
    current = {comparison_key(skill.canonical_title) for skill in profile.skills}
    missing = [skill for skill in get_role_skills(role.role_id) if comparison_key(skill.canonical_title) not in current]
    return missing[:limit]


def _skills_from_practical_gaps(gaps: list[PracticalGapSkill]) -> list[NormalizedSkill]:
    return [
        NormalizedSkill(raw_title=gap.skill, canonical_title=gap.skill, skill_type="TSC", mapped=False)
        for gap in gaps
        if gap.skill
    ]


def _practical_gaps(raw_items, default_source: str) -> list[PracticalGapSkill]:
    if not isinstance(raw_items, list):
        return []
    gaps: list[PracticalGapSkill] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill") or "").strip()
        if not skill:
            continue
        source = item.get("evidence_source") if item.get("evidence_source") in {"conversation", "catalog", "jobs"} else default_source
        gaps.append(
            PracticalGapSkill(
                skill=skill,
                why_required=str(item.get("why_required") or "Required for the target role.").strip(),
                current_signal=str(item.get("current_signal") or "").strip() or None,
                evidence_source=source,
            )
        )
    return gaps


def _balanced(recommendations: list[RecommendedRole], top_k: int) -> list[RecommendedRole]:
    same = [item for item in recommendations if item.domain_type == "same_domain"][:top_k]
    cross = [item for item in recommendations if item.domain_type == "cross_domain"][:top_k]
    combined = same + cross
    if combined:
        return combined
    return recommendations[:top_k]


def _domain_type(profile: ProfileResponse, role: Role) -> str:
    return "same_domain" if role.sector == profile.role.sector else "cross_domain"


def _tier(match_score: float) -> str:
    if match_score >= 0.7:
        return "Adjacent"
    if match_score >= 0.48:
        return "Stretch"
    return "Pivot"
