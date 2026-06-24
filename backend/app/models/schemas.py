from typing import Literal

from pydantic import BaseModel, Field

ProfileSource = Literal["role_template", "resume", "manual"]
SkillType = Literal["TSC", "CCS"]
RealismTier = Literal["Adjacent", "Stretch", "Pivot"]
EvidenceSource = Literal["conversation", "catalog", "jobs"]
AnalysisMode = Literal["openai_catalog", "mock_fallback"]


class Role(BaseModel):
    role_id: str
    role_title: str
    sector: str | None = None
    track: str | None = None
    description: str | None = None


class NormalizedSkill(BaseModel):
    skill_code: str | None = None
    raw_title: str
    canonical_title: str
    skill_type: SkillType = "TSC"
    proficiency_level: int | None = None
    is_emerging: bool = False
    is_casl: bool = False
    mapped: bool = True


class ProfileEdit(BaseModel):
    canonical_title: str
    included: bool = True
    proficiency_level: int | None = None


class ProfileRequest(BaseModel):
    current_role_id: str
    edits: list[ProfileEdit] | None = None


class ProfileResponse(BaseModel):
    role: Role
    skills: list[NormalizedSkill]
    profile_source: ProfileSource
    narrative_summary: str | None = None
    evidence_summary: list[str] = []


class GapSkill(BaseModel):
    skill: NormalizedSkill
    current_proficiency_level: int | None = None
    target_proficiency_level: int | None = None
    gap: int = 0
    priority: float = 0
    status: Literal["Matched", "Proficiency Gap", "Missing"]


class PracticalGapSkill(BaseModel):
    skill: str
    why_required: str
    current_signal: str | None = None
    evidence_source: EvidenceSource


class GapAnalysisRequest(BaseModel):
    current_role_id: str | None = None
    profile: ProfileResponse | None = None
    target_role_id: str


class GapAnalysisResponse(BaseModel):
    current_role: Role | None = None
    target_role: Role
    profile_source: ProfileSource
    match_score: float
    weighted_overlap: float
    matched: list[GapSkill]
    proficiency_gaps: list[GapSkill]
    missing: list[GapSkill]
    transferable: list[NormalizedSkill]
    analysis_mode: AnalysisMode = "mock_fallback"
    ai_summary: str | None = None
    practical_gap_skills: list[PracticalGapSkill] = []


class RecommendRequest(BaseModel):
    current_role_id: str | None = None
    profile: ProfileResponse | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_market_validation: bool = False


class RecommendedRole(BaseModel):
    role: Role
    role_fit_score: float
    match_score: float
    weighted_overlap: float
    tier: RealismTier
    tier_note: str
    domain_type: Literal["same_domain", "cross_domain"] = "same_domain"
    top_missing_skills: list[NormalizedSkill]
    ai_rationale: str | None = None
    required_skills: list[str] = []
    practical_gap_skills: list[PracticalGapSkill] = []


class RecommendResponse(BaseModel):
    profile_source: ProfileSource
    recommendations: list[RecommendedRole]


class MarketRequest(BaseModel):
    target_role_id: str
    location: str = "Singapore"
    use_apify: bool = False
    max_jobs: int = Field(default=10, ge=1, le=50)


class MarketBucket(BaseModel):
    label: str
    skills: list[str]


class JobPosting(BaseModel):
    title: str
    company: str
    location: str
    url: str | None = None
    summary: str
    extracted_skills: list[str]


class PracticalSkillInsight(BaseModel):
    skill: str
    count: int
    note: str


class MarketResponse(BaseModel):
    target_role: Role
    jobs_analysed: int
    mode: Literal["demo", "apify"]
    notice: str | None = None
    jobs: list[JobPosting] = []
    mapped_skill_frequency: dict[str, int]
    raw_tool_frequency: dict[str, int]
    practical_skill_insights: list[PracticalSkillInsight] = []
    buckets: list[MarketBucket]


class LearningPlanRequest(BaseModel):
    current_role_id: str | None = None
    profile: ProfileResponse | None = None
    target_role_id: str
    include_market_validation: bool = True
    duration_days: int = 30


class WeeklyPlan(BaseModel):
    week: int
    theme: str
    tasks: list[str]


class LearningPlanResponse(BaseModel):
    target_role: Role
    profile_source: ProfileSource
    focus_skills: list[str]
    weekly_plan: list[WeeklyPlan]
    daily_tasks: list[str]
    mini_project: str
    final_portfolio_task: str
    dataset_evidence: list[str]
    market_evidence: list[str]
    honesty_line: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SkillAssessment(BaseModel):
    skill: NormalizedSkill
    inferred_level: int | None = None
    evidence: str | None = None
    confidence: float = 0.5
    needs_follow_up: bool = False


class ProfileConversationRequest(BaseModel):
    messages: list[ChatMessage] = []
    resume_text: str | None = None


class ProfileConversationResponse(BaseModel):
    mode: Literal["openai", "mock"]
    assistant_message: str
    follow_up_questions: list[str]
    suggested_replies: list[str] = []
    mapped_role: Role
    profile: ProfileResponse
    skill_assessments: list[SkillAssessment]
    current_role_confidence: float = 0
    ready_to_explore: bool = False
    evidence_summary: list[str] = []


class CourseSearchRequest(BaseModel):
    target_role_id: str
    focus_skills: list[str]
    location: str = "Singapore"


class CourseRecommendation(BaseModel):
    title: str
    provider: str
    url: str
    skills: list[str]
    reason: str


class CourseSearchResponse(BaseModel):
    mode: Literal["openai_web_search", "demo"]
    notice: str | None = None
    courses: list[CourseRecommendation]
