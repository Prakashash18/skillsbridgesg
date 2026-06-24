from app.data.repository import get_role
from app.llm.client import LLMClient
from app.models.schemas import CourseRecommendation, CourseSearchResponse


def find_courses(target_role_id: str, focus_skills: list[str], location: str = "Singapore") -> CourseSearchResponse:
    role = get_role(target_role_id)
    skills = focus_skills[:5] or ["role fundamentals"]
    client = LLMClient()
    result = client.json_response(
        instructions=(
            "Find Singapore-relevant courses for the target role and focus skills. Use web search if available. "
            "Return strict JSON: {courses:[{title,provider,url,skills,reason}]}. Prefer SkillsFuture, local polytechnics, universities, and reputable online providers."
        ),
        payload={"target_role": role.model_dump(), "focus_skills": skills, "location": location},
        use_web_search=True,
    )
    if result and isinstance(result.get("courses"), list):
        courses = [CourseRecommendation(**course) for course in result["courses"][:6] if course.get("title") and course.get("url")]
        if courses:
            return CourseSearchResponse(mode="openai_web_search", courses=courses)
    return CourseSearchResponse(
        mode="demo",
        notice=(
            "Live web course search is temporarily unavailable, so these are SkillsFuture search starting points."
            if client.available
            else "Demo mode: add OPENAI_API_KEY to search the web for live course recommendations."
        ),
        courses=[
            CourseRecommendation(
                title=f"{skill} for {role.role_title}",
                provider="MySkillsFuture / local providers",
                url=f"https://www.myskillsfuture.gov.sg/content/portal/en/training-exchange/course-landing.html",
                skills=[skill],
                reason=f"Use this as a search starting point for Singapore-funded courses covering {skill}.",
            )
            for skill in skills
        ],
    )
