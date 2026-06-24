import re

from app.data.repository import get_role, get_role_skills, list_roles, list_unique_skills
from app.llm.client import LLMClient
from app.models.schemas import NormalizedSkill, ProfileConversationResponse, ProfileEdit, ProfileResponse, Role, SkillAssessment
from app.services.normalize import comparison_key
from app.services.profile import build_profile


def converse_about_profile(messages, resume_text: str | None = None) -> ProfileConversationResponse:
    """AI-first intake: a single grounded call steers the conversation, maps the
    current role, and infers TSC/CCS skills from the catalog. Falls back to the
    deterministic heuristic flow when no key is set or the AI call fails."""
    client = LLMClient()
    if client.available:
        ai = _ai_converse(messages, resume_text, client)
        if ai:
            return ai
    return _fallback_converse(messages, resume_text)


def _ai_converse(messages, resume_text: str | None, client: LLMClient) -> ProfileConversationResponse | None:
    roles = list_roles()
    source_text = " ".join([m.content for m in messages if m.role == "user"] + [resume_text or ""]).lower()
    candidates = _rank_role_candidates(source_text, roles, limit=25) if source_text.strip() else roles
    catalog = list_unique_skills(limit=160)
    result = client.json_response(
        instructions=(
            "You are SkillBridge SG's career intake assistant. Your goal is to understand the person's real "
            "experience by steering a warm, natural conversation. Be concise: reply in 1-3 short sentences, ask "
            "ONE focused question at a time, and never dump a list of questions or paste long explanations. "
            "Map their work to the closest SkillsFuture role from the candidates, and infer the TSC/CCS skills they "
            "actually demonstrate, grounded ONLY in the provided skills catalogue (use exact catalogue titles). "
            "If they only greeted you, ask what they do day-to-day. If they ask what a term means, answer in one "
            "sentence. Set ready_to_explore true only once you can confidently name their role and at least 3 skills. "
            "Return strict JSON with keys: assistant_message (string), suggested_replies (2-5 short clickable answer "
            "options the user could tap, each <= 6 words, phrased in first person like 'Yes, I lead delivery'), "
            "mapped_role_id (one candidate role_id), current_role_confidence (0-1), ready_to_explore (boolean), "
            "evidence_summary (up to 4 short signal strings), inferred_skills (array of {skill_title (must match a "
            "catalogue title), skill_type ('TSC' or 'CCS'), proficiency_level (1-5), evidence (short), confidence (0-1)})."
        ),
        payload={
            "conversation": [m.model_dump() for m in messages],
            "resume_text": resume_text or "",
            "candidate_roles": [
                {"role_id": r.role_id, "role_title": r.role_title, "sector": r.sector, "track": r.track, "description": r.description}
                for r in candidates
            ],
            "skills_catalogue": [{"title": s.canonical_title, "type": s.skill_type} for s in catalog],
        },
    )
    if not isinstance(result, dict) or not str(result.get("assistant_message") or "").strip():
        return None

    role = _resolve_role(result.get("mapped_role_id"), candidates, roles, source_text)
    inferred = _coerce_inferred_skills(result.get("inferred_skills"), catalog)
    profile, assessments = _profile_from_inferred(role, inferred, source_text, resume_text)
    confidence = _bounded(result.get("current_role_confidence"), 0.5)
    # Unlock exploration when the AI says so, or once it is reasonably confident
    # about the role and has grounded at least 3 catalogue skills — so a detailed
    # answer doesn't get trapped behind extra questions.
    ready = (bool(result.get("ready_to_explore")) or confidence >= 0.6) and len(profile.skills) >= 3
    evidence = [str(item).strip() for item in result.get("evidence_summary", []) if str(item).strip()][:4]
    replies = [str(item).strip() for item in result.get("suggested_replies", []) if str(item).strip()][:5]
    return _response(
        mode="openai",
        assistant_message=str(result["assistant_message"]).strip(),
        questions=replies,
        role=role,
        profile=profile,
        assessments=assessments,
        confidence=confidence,
        ready=ready,
        evidence=evidence,
        suggested_replies=replies,
    )


def _resolve_role(role_id, candidates: list[Role], roles: list[Role], source_text: str) -> Role:
    wanted = str(role_id or "").strip()
    for role in candidates + roles:
        if role.role_id == wanted:
            return role
    return _infer_role_from_candidates(source_text, roles) if source_text.strip() else _default_role(roles)


def _coerce_inferred_skills(raw, catalog: list[NormalizedSkill]) -> list[dict]:
    if not isinstance(raw, list):
        return []
    by_key = {comparison_key(skill.canonical_title): skill for skill in catalog}
    inferred: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("skill_title") or "").strip()
        if not title:
            continue
        key = comparison_key(title)
        if key in seen:
            continue
        seen.add(key)
        match = by_key.get(key)
        level = item.get("proficiency_level")
        try:
            level = max(1, min(5, int(level)))
        except (TypeError, ValueError):
            level = 3
        confidence = _bounded(item.get("confidence"), 0.6)
        skill_type = str(item.get("skill_type") or (match.skill_type if match else "TSC")).upper()
        skill = NormalizedSkill(
            skill_code=match.skill_code if match else None,
            raw_title=title,
            canonical_title=match.canonical_title if match else title,
            skill_type="CCS" if skill_type == "CCS" else "TSC",
            proficiency_level=level,
            is_emerging=match.is_emerging if match else False,
            is_casl=match.is_casl if match else False,
            mapped=match is not None,
        )
        inferred.append({"skill": skill, "evidence": str(item.get("evidence") or "").strip(), "confidence": confidence})
    return inferred


def _profile_from_inferred(role: Role, inferred: list[dict], source_text: str, resume_text: str | None) -> tuple[ProfileResponse, list[SkillAssessment]]:
    if not inferred:
        # Safety net: if the AI named no catalogue skills, fall back to the role template
        # so downstream gap/recommendation still has skills to reason about.
        base = build_profile(role.role_id)
        assessments = [
            SkillAssessment(skill=skill, inferred_level=skill.proficiency_level, evidence="Mapped from role template.", confidence=0.45, needs_follow_up=True)
            for skill in base.skills
        ]
        base.narrative_summary = _profile_summary(source_text, _evidence_summary(source_text))
        base.evidence_summary = _evidence_summary(source_text)
        return base, assessments

    skills = [item["skill"] for item in inferred]
    assessments = [
        SkillAssessment(
            skill=item["skill"],
            inferred_level=item["skill"].proficiency_level,
            evidence=item["evidence"] or "Inferred from the conversation.",
            confidence=item["confidence"],
            needs_follow_up=item["confidence"] < 0.6,
        )
        for item in inferred
    ]
    profile = ProfileResponse(
        role=role,
        skills=skills,
        profile_source="resume" if (resume_text or "").strip() else "manual",
        narrative_summary=_profile_summary(source_text, _evidence_summary(source_text)),
        evidence_summary=_evidence_summary(source_text),
    )
    return profile, assessments


def _bounded(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _fallback_converse(messages, resume_text: str | None = None) -> ProfileConversationResponse:
    roles = list_roles()
    user_messages = [message.content for message in messages if message.role == "user"]
    last_user_message = user_messages[-1].strip().lower() if user_messages else ""
    profile_messages = user_messages[:-1] if _is_definition_question(last_user_message) and len(user_messages) > 1 else user_messages
    source_text = " ".join(profile_messages + [resume_text or ""]).lower()
    evidence = _evidence_summary(source_text)
    education_signal = _education_signal(source_text)
    client = LLMClient()
    role = _infer_role_with_ai(source_text, roles, client) or _infer_role_from_candidates(source_text, roles)
    base_profile = build_profile(role.role_id)
    assessments = _infer_skill_depths(base_profile, source_text)
    edits = [
        ProfileEdit(canonical_title=item.skill.canonical_title, included=True, proficiency_level=item.inferred_level or item.skill.proficiency_level)
        for item in assessments
    ]
    profile = build_profile(role.role_id, edits=edits)
    profile.narrative_summary = _profile_summary(source_text, evidence)
    profile.evidence_summary = evidence
    follow_ups = [item.skill.canonical_title for item in assessments if item.needs_follow_up][:3]
    confidence = _role_confidence(source_text, role)
    ready = confidence >= 0.55 and len(evidence) >= 2

    if _is_greeting(last_user_message):
        return _response(
            mode="mock",
            assistant_message="Hi. I’ll help identify your current role first, then we can explore realistic next roles. What is your job title today, and what are 2-3 things you spend most of your week doing?",
            questions=[
                "What is your current job title or closest title?",
                "What work takes most of your week: projects, sales, operations, analysis, people management, systems, or something else?",
            ],
            role=role,
            profile=profile,
            assessments=assessments,
            confidence=0,
            ready=False,
            evidence=[],
        )

    if _is_definition_question(last_user_message):
        answer = _answer_definition_question(last_user_message, profile, client, messages, resume_text)
        return _response(
            mode=answer["mode"],
            assistant_message=answer["assistant_message"],
            questions=answer["questions"],
            role=role,
            profile=profile,
            assessments=assessments,
            confidence=confidence,
            ready=ready,
            evidence=evidence,
        )

    if _asks_why(last_user_message) and not ready:
        return _response(
            mode="mock",
            assistant_message="Fair question. I have a starting signal, but I should not lock in the SkillsFuture role until I understand your day-to-day work. Tell me the learners you support, the subjects or tools you teach, and whether you mainly deliver lessons, design curriculum, assess learners, or manage programmes.",
            questions=[
                "Who do you teach or support: ITE students, adult learners, children, corporate learners, or another group?",
                "Which subjects, tools, or technologies do you teach hands-on?",
                "Do you mostly deliver classes, design curriculum, assess learners, manage programmes, or coach projects?",
            ],
            role=role,
            profile=profile,
            assessments=assessments,
            confidence=confidence,
            ready=False,
            evidence=evidence,
        )

    if not ready:
        if education_signal:
            return _response(
                mode="mock",
                assistant_message="That helps. I’m reading this as an education or training role, but I need one more work detail before I map it to the official SkillsFuture catalogue. Are you mainly teaching learners, designing courseware, assessing competency, or running learning programmes?",
                questions=[
                    "Who are your learners and what level are they at?",
                    "What do you teach: programming, IoT, robotics, curriculum design, assessment, or something else?",
                    "What do you personally own each week: lesson delivery, course design, learner assessment, labs, projects, or programme coordination?",
                ],
                role=role,
                profile=profile,
                assessments=assessments,
                confidence=confidence,
                ready=False,
                evidence=evidence,
            )
        return _response(
            mode="mock",
            assistant_message="I have a starting signal, but I need a little more work context before I map you to the SkillsFuture role catalogue.",
            questions=[
                "What is your current job title?",
                "What are the main tasks or decisions you handle weekly?",
                "Which tools, systems, clients, or industry domain are involved?",
            ],
            role=role,
            profile=profile,
            assessments=assessments,
            confidence=confidence,
            ready=False,
            evidence=evidence,
        )

    llm_result = client.json_response(
        instructions=(
            "You are SkillBridge SG's career intake assistant. Return strict JSON with keys "
            "assistant_message and follow_up_questions. Be conversational and explain the current-role mapping briefly. "
            "Ask concise questions only about unclear scope and depth of experience. Do not invent official skills."
        ),
        payload={
            "roles": [role.model_dump() for role in roles],
            "mapped_role": role.model_dump(),
            "current_role_confidence": confidence,
            "evidence_summary": evidence,
            "skill_assessments": [item.model_dump() for item in assessments],
            "resume_text": resume_text,
            "messages": [message.model_dump() for message in messages],
        },
    )
    if llm_result:
        assistant_message = str(llm_result.get("assistant_message", "")).strip() or _assistant_message(role.role_title, follow_ups)
        questions = [str(item) for item in llm_result.get("follow_up_questions", [])][:4] or _questions(follow_ups)
        mode = "openai"
    elif education_signal:
        assistant_message = _education_assistant_message(role.role_title)
        questions = _education_questions(source_text)
        mode = "mock"
    else:
        assistant_message = _assistant_message(role.role_title, follow_ups)
        questions = _questions(follow_ups)
        mode = "mock"
    return _response(
        mode=mode,
        assistant_message=assistant_message,
        questions=questions,
        role=role,
        profile=profile,
        assessments=assessments,
        confidence=confidence,
        ready=True,
        evidence=evidence,
    )


def _infer_role(text: str):
    roles = list_roles()
    return _infer_role_from_candidates(text, roles)


def _infer_role_from_candidates(text: str, roles):
    if not text.strip():
        return _default_role(roles)
    best = roles[0]
    best_score = -1
    for role in roles:
        role_text = " ".join([role.role_title, role.sector or "", role.track or "", role.description or ""]).lower()
        terms = [role.role_title.lower(), role.track.lower() if role.track else ""]
        score = 3 * sum(1 for term in terms if term and _has_phrase(text, term))
        for token in role.role_title.lower().split():
            score += 2 if len(token) > 3 and _has_phrase(text, token) else 0
        for token in (role.description.lower() if role.description else "").split():
            score += 1 if len(token) > 6 and _has_phrase(text, token) else 0
        score += _domain_boost(text, role_text)
        if score > best_score:
            best = role
            best_score = score
    return best


def _infer_role_with_ai(text: str, roles, client: LLMClient):
    if not client.available or not text.strip() or len(text.split()) < 5:
        return None
    candidates = _rank_role_candidates(text, roles, limit=25)
    result = client.json_response(
        instructions=(
            "You map a user's current work story to the closest official SkillsFuture role. "
            "Choose exactly one role_id from the provided candidates. Prefer the user's actual weekly work over job-title keywords. "
            "For lecturers or trainers, distinguish teaching facilitation, curriculum/courseware design, learning technology, assessment, and programme management. "
            "Return strict JSON with role_id, confidence from 0 to 1, and rationale."
        ),
        payload={
            "user_profile_text": text,
            "candidate_roles": [role.model_dump() for role in candidates],
        },
    )
    if not result:
        return None
    role_id = str(result.get("role_id", "")).strip()
    return next((role for role in candidates if role.role_id == role_id), None)


def _rank_role_candidates(text: str, roles, limit: int = 25):
    scored = []
    for role in roles:
        role_text = " ".join([role.role_title, role.sector or "", role.track or "", role.description or ""]).lower()
        score = 0
        for token in role.role_title.lower().split():
            score += 2 if len(token) > 3 and _has_phrase(text, token) else 0
        for token in (role.description.lower() if role.description else "").split():
            score += 1 if len(token) > 6 and _has_phrase(text, token) else 0
        score += _domain_boost(text, role_text)
        scored.append((score, role))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [role for _, role in scored[:limit]]


def _default_role(roles):
    preferred_titles = ["Associate Business Analyst", "Business Development Manager", "Account Operations Manager"]
    for title in preferred_titles:
        for role in roles:
            if role.role_title.lower() == title.lower():
                return role
    preferred_fragments = ["business analyst", "project manager", "operations manager", "business development manager"]
    for fragment in preferred_fragments:
        for role in roles:
            if fragment in role.role_title.lower():
                return role
    return roles[0]


def _infer_skill_depths(profile: ProfileResponse, text: str) -> list[SkillAssessment]:
    assessments = []
    for skill in get_role_skills(profile.role.role_id):
        key = comparison_key(skill.canonical_title)
        mentioned = any(part in text for part in key.split())
        strong_words = ["led", "owned", "managed", "designed", "built", "deployed", "advanced", "senior"]
        level = skill.proficiency_level
        confidence = 0.45
        if mentioned:
            confidence = 0.72
            if any(word in text for word in strong_words):
                level = min(5, max(level or 3, 4))
        assessments.append(
            SkillAssessment(
                skill=skill,
                inferred_level=level,
                evidence="Mentioned in resume/chat." if mentioned else "Mapped from role template; needs confirmation.",
                confidence=confidence,
                needs_follow_up=confidence < 0.65,
            )
        )
    return assessments


def _profile_summary(text: str, evidence: list[str]) -> str:
    clean = " ".join(text.split())
    if len(clean) > 420:
        clean = f"{clean[:417]}..."
    if evidence:
        return f"User-described work: {clean}. Signals: {'; '.join(evidence)}"
    return f"User-described work: {clean}" if clean else ""


def _assistant_message(role_title: str, follow_ups: list[str]) -> str:
    if follow_ups:
        return f"Based on what you described, your current role looks closest to {role_title}. Before we explore next roles, I want to confirm your depth in {', '.join(follow_ups)}."
    return f"Based on what you described, your current role looks closest to {role_title}. I have enough signal to suggest adjacent and cross-domain roles."


def _education_assistant_message(role_title: str) -> str:
    return (
        f"Thanks, that is enough to create a first working profile. I would map your current work closest to {role_title} for now, "
        "with teaching delivery, learner support, and digital or technical content as the main signals. Before we explore next roles, I’ll keep the mapping provisional so we can refine it if your work is more curriculum design, assessment, or programme management."
    )


def _answer_definition_question(last_user_message: str, profile: ProfileResponse, client: LLMClient, messages, resume_text: str | None) -> dict:
    term = _extract_definition_term(last_user_message)
    profile_terms = [skill.canonical_title for skill in profile.skills]
    matched_term = _closest_profile_term(term, profile_terms) or term
    if client.available:
        result = client.json_response(
            instructions=(
                "You are SkillBridge SG's career intake assistant. The user asked what a skill or role term means. "
                "Answer the question directly in plain language, relate it to their current role context, and do not remap the role unless asked. "
                "If the official catalogue term seems less relevant than their actual work, say so gently. "
                "Return strict JSON with assistant_message and follow_up_questions."
            ),
            payload={
                "question": last_user_message,
                "detected_term": matched_term,
                "current_role": profile.role.model_dump(),
                "profile_skills": profile_terms,
                "resume_text": resume_text,
                "messages": [message.model_dump() for message in messages],
            },
        )
        if result:
            return {
                "mode": "openai",
                "assistant_message": str(result.get("assistant_message", "")).strip() or _fallback_definition_answer(matched_term, profile.role.role_title),
                "questions": [str(item) for item in result.get("follow_up_questions", [])][:3] or _definition_followups(profile.role.role_title),
            }
    return {
        "mode": "mock",
        "assistant_message": _fallback_definition_answer(matched_term, profile.role.role_title),
        "questions": _definition_followups(profile.role.role_title),
    }


def _fallback_definition_answer(term: str, role_title: str) -> str:
    lowered = term.lower()
    if "talent capability" in lowered:
        return (
            "Talent capability development means helping people build the skills, confidence, and readiness needed for a role or programme. "
            "In HR it can mean workforce capability planning; in your lecturer context it is closer to identifying learner skill gaps, designing learning activities, and checking whether learners can apply the skill. "
            f"For your current profile as {role_title}, I would not treat it as the main signal unless you also own programme-wide capability planning."
        )
    if "competency framework" in lowered:
        return (
            "A competency framework is a structured description of what someone must know and be able to do at different proficiency levels. "
            "For your IoT modules, this could mean defining outcomes like wiring sensors, writing Python scripts, troubleshooting devices, and explaining the design choices."
        )
    if "workforce data" in lowered:
        return (
            "Workforce data management is about collecting and using people, skills, or learning data to make decisions. "
            "For a lecturer, this may only be relevant if you track learner progress, assessment results, completion data, or programme outcomes."
        )
    return (
        f"{term.strip().title() or 'That term'} is a catalogue skill label, so I would translate it into the work it represents before using it in your profile. "
        f"For your current role as {role_title}, tell me whether you actually do that work weekly, or whether your stronger evidence is teaching, curriculum design, assessment, and IoT/Python lab delivery."
    )


def _definition_followups(role_title: str) -> list[str]:
    return [
        f"Should I keep this as part of your {role_title} profile, or focus more on teaching and curriculum design?",
        "Do you personally design learner outcomes or mostly deliver the module?",
        "Do you assess learners formally through rubrics, projects, or competency checks?",
    ]


def _is_definition_question(text: str) -> bool:
    lowered = text.strip().lower()
    starters = ("what is ", "what's ", "whats ", "what does ", "explain ", "meaning of ", "define ")
    return lowered.endswith("?") and lowered.startswith(starters) or lowered.startswith(starters)


def _extract_definition_term(text: str) -> str:
    lowered = text.strip().lower().rstrip("?")
    for prefix in ["what is ", "what's ", "whats ", "what does ", "explain ", "meaning of ", "define "]:
        if lowered.startswith(prefix):
            term = lowered[len(prefix) :]
            term = term.replace(" mean", "").replace(" means", "").strip()
            return term
    return lowered


def _closest_profile_term(term: str, profile_terms: list[str]) -> str | None:
    key = comparison_key(term)
    if not key:
        return None
    for candidate in profile_terms:
        candidate_key = comparison_key(candidate)
        if key == candidate_key or key in candidate_key or candidate_key in key:
            return candidate
    term_tokens = {token for token in key.split() if len(token) > 3}
    best = None
    best_overlap = 0
    for candidate in profile_terms:
        candidate_tokens = {token for token in comparison_key(candidate).split() if len(token) > 3}
        overlap = len(term_tokens & candidate_tokens)
        if overlap > best_overlap:
            best = candidate
            best_overlap = overlap
    return best if best_overlap else None


def _education_questions(text: str) -> list[str]:
    questions = [
        "What share of your week is live teaching or lab facilitation versus curriculum/courseware design?",
        "Which technologies do you teach hands-on, and what level do learners reach by the end?",
        "Do you assess competency, mentor projects, or manage programmes as part of the role?",
    ]
    if not _contains_any(text, ["assessment", "assess", "competency"]):
        return questions
    return [
        "How formal is your assessment work: class exercises, project rubrics, certification, or competency-based assessment?",
        "Which technologies do you teach hands-on, and what level do learners reach by the end?",
        "Do you also design curriculum/courseware or mainly deliver and coach learners?",
    ]


def _questions(skills: list[str]) -> list[str]:
    if not skills:
        return ["Which role title best describes your current work?", "Which skills have you used hands-on in the last 12 months?"]
    return [f"For {skill}, what have you personally delivered and at what depth: assisted, owned, or led?" for skill in skills]


def _response(mode, assistant_message, questions, role, profile, assessments, confidence, ready, evidence, suggested_replies=None):
    return ProfileConversationResponse(
        mode=mode,
        assistant_message=assistant_message,
        follow_up_questions=questions,
        suggested_replies=suggested_replies or [],
        mapped_role=role,
        profile=profile,
        skill_assessments=assessments,
        current_role_confidence=round(confidence, 2),
        ready_to_explore=ready,
        evidence_summary=evidence,
    )


def _is_greeting(text: str) -> bool:
    return text.strip().lower() in {"hi", "hello", "hey", "hiya", "yo", "good morning", "good afternoon", "good evening"}


def _asks_why(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered in {"why", "why?", "why/", "how come"} or lowered.startswith("why ")


def _evidence_summary(text: str) -> list[str]:
    signals = []
    buckets = {
        "role/title": ["manager", "analyst", "engineer", "executive", "consultant", "lead", "specialist", "developer", "designer", "lecturer", "teacher", "instructor", "trainer", "educator", "facilitator"],
        "work activities": ["manage", "managed", "lead", "led", "build", "built", "analyse", "analyze", "coordinate", "sell", "support", "operate", "design", "deliver", "teach", "teaching", "train", "training", "instruct", "mentor", "coach", "assess", "curriculum", "lesson", "lessons", "lab", "labs"],
        "tools/systems": ["sql", "excel", "power bi", "tableau", "jira", "python", "sap", "crm", "salesforce", "dashboard", "programming", "coding", "iot", "arduino", "raspberry pi", "microbit", "robotics"],
        "domain": ["finance", "logistics", "healthcare", "energy", "solar", "retail", "it", "software", "data", "marketing", "sales", "hr", "education", "ite", "polytechnic", "school", "edtech", "children", "kids", "youth", "student", "students", "learner", "learners"],
    }
    for label, terms in buckets.items():
        matched = [term for term in terms if _has_phrase(text, term)]
        if matched:
            signals.append(f"{label}: {', '.join(matched[:3])}")
    return signals[:4]


def _role_confidence(text: str, role) -> float:
    if not text.strip():
        return 0
    evidence_count = len(_evidence_summary(text))
    title_tokens = [token for token in role.role_title.lower().split() if len(token) > 3]
    title_hits = sum(1 for token in title_tokens if _has_phrase(text, token))
    word_count = len([word for word in text.split() if len(word) > 2])
    confidence = 0.15 * evidence_count + 0.08 * title_hits + min(0.25, word_count / 80)
    if _education_signal(text):
        confidence += 0.12
    if _programming_or_iot_signal(text) and _education_signal(text):
        confidence += 0.08
    return min(0.95, confidence)


def _domain_boost(text: str, role_text: str) -> int:
    score = 0
    education = _education_signal(text)
    programming = _programming_or_iot_signal(text)
    young_learners = _contains_any(text, ["kids", "children", "youth", "school", "students", "learners"])
    adult_or_ite = _contains_any(text, ["ite", "adult", "polytechnic", "institute of technical education"])
    delivery = _contains_any(text, ["teach", "teaching", "deliver", "class", "classes", "lesson", "lessons", "lab", "labs", "mentor", "coach"])
    course_design = _contains_any(text, ["curriculum", "courseware", "design", "designed", "syllabus", "lesson plan", "learning materials"])

    if education:
        if "training and adult education" in role_text:
            score += 18
        if "adult education" in role_text:
            score += 8
        if _contains_any(role_text, ["learning facilitator", "learning solutionist", "learning consultant", "courseware developer", "curriculum lead", "learning technology designer"]):
            score += 10
        if _contains_any(role_text, ["educator", "teacher", "instructor", "trainer", "facilitator", "learning"]):
            score += 5
        if delivery and "learning facilitator" in role_text:
            score += 12
        if course_design and _contains_any(role_text, ["courseware developer", "curriculum lead"]):
            score += 10
    if programming:
        if _contains_any(role_text, ["learning technology designer", "courseware developer", "curriculum lead", "learning facilitator"]):
            score += 8
        if "learning technology designer" in role_text:
            score += 6
        if _contains_any(role_text, ["software", "embedded systems", "programmer", "infocomm technology"]):
            score += 4
    if young_learners and not adult_or_ite:
        if _contains_any(role_text, ["early childhood", "youth work", "arts education"]):
            score += 6
    if adult_or_ite and "training and adult education" in role_text:
        score += 8
    return score


def _education_signal(text: str) -> bool:
    return _contains_any(
        text,
        [
            "lecturer",
            "teacher",
            "instructor",
            "trainer",
            "educator",
            "facilitator",
            "teach",
            "teaching",
            "train",
            "training",
            "curriculum",
            "lesson",
            "ite",
            "polytechnic",
            "school",
            "students",
            "student",
            "learners",
            "learner",
            "kids",
            "children",
        ],
    )


def _programming_or_iot_signal(text: str) -> bool:
    return _contains_any(text, ["programming", "coding", "python", "iot", "arduino", "raspberry pi", "microbit", "robotics", "software"])


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(_has_phrase(text, term) for term in terms)


def _has_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    escaped = re.escape(phrase)
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
