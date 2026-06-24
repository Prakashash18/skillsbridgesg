import io

import pdfplumber
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.data.ingest import run_ingest
from app.data.db import connect
from app.data.repository import get_key_tasks, get_role, get_role_skills, list_roles
from app.models.schemas import CourseSearchRequest, GapAnalysisRequest, LearningPlanRequest, MarketRequest, ProfileConversationRequest, ProfileRequest, RecommendRequest
from app.services.career_chat import converse_about_profile
from app.services.courses import find_courses
from app.services.gap_analysis import analyse_gap
from app.services.market import validate_market
from app.services.plan import build_learning_plan
from app.services.profile import build_profile
from app.services.recommend import recommend_roles

router = APIRouter()


@router.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported. Upload a .pdf file.")
    content = await file.read()
    pages = 0
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse PDF: {exc}") from exc
    return {"text": text.strip(), "pages": pages}


@router.post("/ingest")
def ingest() -> dict:
    return run_ingest()


@router.get("/catalog/status")
def catalog_status() -> dict:
    with connect() as conn:
        roles_count = conn.execute("SELECT COUNT(*) AS c FROM roles").fetchone()["c"]
        role_skills_count = conn.execute("SELECT COUNT(*) AS c FROM role_skills").fetchone()["c"]
        unique_skills_count = conn.execute("SELECT COUNT(*) AS c FROM unique_skills").fetchone()["c"]
        mappings_count = conn.execute("SELECT COUNT(*) AS c FROM tsc_to_unique").fetchone()["c"]
    mode = "skillsfuture_workbooks" if roles_count > 100 else "demo_seed"
    return {
        "mode": mode,
        "counts": {
            "roles": roles_count,
            "role_skills": role_skills_count,
            "unique_skills": unique_skills_count,
            "skill_mappings": mappings_count,
        },
    }


@router.get("/roles")
def roles(q: str | None = None, sector: str | None = None, track: str | None = None):
    return list_roles(q=q, sector=sector, track=track)


@router.get("/roles/{role_id}")
def role_detail(role_id: str):
    try:
        role = get_role(role_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Role not found") from None
    return {"role": role, "key_tasks": get_key_tasks(role_id), "skills": get_role_skills(role_id)}


@router.post("/profile")
def profile(payload: ProfileRequest):
    try:
        return build_profile(payload.current_role_id, payload.edits)
    except KeyError:
        raise HTTPException(status_code=404, detail="Role not found") from None


@router.post("/ai/profile-conversation")
def profile_conversation(payload: ProfileConversationRequest):
    return converse_about_profile(payload.messages, payload.resume_text)


@router.post("/gap-analysis")
def gap_analysis(payload: GapAnalysisRequest):
    try:
        profile = payload.profile or build_profile(payload.current_role_id or "")
        return analyse_gap(profile, payload.target_role_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Role not found") from None


@router.post("/recommend-roles")
def recommend(payload: RecommendRequest):
    profile = payload.profile or build_profile(payload.current_role_id or "")
    return recommend_roles(profile, payload.top_k)


@router.post("/market-validate")
def market(payload: MarketRequest):
    return validate_market(payload.target_role_id, payload.location, payload.max_jobs, payload.use_apify)


@router.post("/course-search")
def course_search(payload: CourseSearchRequest):
    return find_courses(payload.target_role_id, payload.focus_skills, payload.location)


@router.post("/learning-plan")
def plan(payload: LearningPlanRequest):
    profile = payload.profile or build_profile(payload.current_role_id or "")
    return build_learning_plan(profile, payload.target_role_id, payload.include_market_validation)
