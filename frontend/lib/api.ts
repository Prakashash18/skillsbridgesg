const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type ProfileSource = "role_template" | "resume" | "manual";
export type Tier = "Adjacent" | "Stretch" | "Pivot";

export type Role = {
  role_id: string;
  role_title: string;
  sector?: string;
  track?: string;
  description?: string;
};

export type Skill = {
  skill_code?: string | null;
  raw_title: string;
  canonical_title: string;
  skill_type: "TSC" | "CCS";
  proficiency_level?: number | null;
  is_emerging: boolean;
  is_casl: boolean;
  mapped: boolean;
};

export type Profile = {
  role: Role;
  skills: Skill[];
  profile_source: ProfileSource;
  narrative_summary?: string | null;
  evidence_summary?: string[];
};

export type GapSkill = {
  skill: Skill;
  current_proficiency_level?: number | null;
  target_proficiency_level?: number | null;
  gap: number;
  priority: number;
  status: "Matched" | "Proficiency Gap" | "Missing";
};

export type PracticalGapSkill = {
  skill: string;
  why_required: string;
  current_signal?: string | null;
  evidence_source: "conversation" | "catalog" | "jobs";
};

export type GapAnalysis = {
  current_role?: Role;
  target_role: Role;
  profile_source: ProfileSource;
  match_score: number;
  weighted_overlap: number;
  matched: GapSkill[];
  proficiency_gaps: GapSkill[];
  missing: GapSkill[];
  transferable: Skill[];
  analysis_mode?: "openai_catalog" | "mock_fallback";
  ai_summary?: string | null;
  practical_gap_skills?: PracticalGapSkill[];
};

export type Recommendation = {
  role: Role;
  role_fit_score: number;
  match_score: number;
  weighted_overlap: number;
  tier: Tier;
  tier_note: string;
  domain_type: "same_domain" | "cross_domain";
  top_missing_skills: Skill[];
  ai_rationale?: string | null;
  required_skills?: string[];
  practical_gap_skills?: PracticalGapSkill[];
};

export type JobPosting = {
  title: string;
  company: string;
  location: string;
  url?: string | null;
  summary: string;
  extracted_skills: string[];
};

export type PracticalSkillInsight = {
  skill: string;
  count: number;
  note: string;
};

export type Market = {
  target_role: Role;
  jobs_analysed: number;
  mode: "demo" | "apify";
  notice?: string;
  jobs: JobPosting[];
  mapped_skill_frequency: Record<string, number>;
  raw_tool_frequency: Record<string, number>;
  practical_skill_insights: PracticalSkillInsight[];
  buckets: { label: string; skills: string[] }[];
};

export type Plan = {
  target_role: Role;
  profile_source: ProfileSource;
  focus_skills: string[];
  weekly_plan: { week: number; theme: string; tasks: string[] }[];
  daily_tasks: string[];
  mini_project: string;
  final_portfolio_task: string;
  dataset_evidence: string[];
  market_evidence: string[];
  honesty_line: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ProfileConversation = {
  mode: "openai" | "mock";
  model?: string | null;
  assistant_message: string;
  follow_up_questions: string[];
  suggested_replies: string[];
  mapped_role: Role;
  profile: Profile;
  skill_assessments: {
    skill: Skill;
    inferred_level?: number | null;
    evidence?: string | null;
    confidence: number;
    needs_follow_up: boolean;
  }[];
  current_role_confidence: number;
  ready_to_explore: boolean;
  evidence_summary: string[];
};

export type CourseRecommendation = {
  title: string;
  provider: string;
  url: string;
  skills: string[];
  reason: string;
};

export type CourseSearch = {
  mode: "openai_web_search" | "demo";
  notice?: string | null;
  courses: CourseRecommendation[];
};

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method: "POST", body: form });
  } catch {
    throw new Error("Cannot reach the SkillBridge backend. Check that FastAPI is running on http://localhost:8000.");
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); detail = body.detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {})
      }
    });
  } catch {
    throw new Error("Cannot reach the SkillBridge backend. Check that FastAPI is running on http://localhost:8000.");
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  ingest: () => request<{ mode: string; counts: Record<string, number> }>("/api/ingest", { method: "POST", body: "{}" }),
  catalogStatus: () => request<{ mode: string; counts: Record<string, number> }>("/api/catalog/status"),
  roles: () => request<Role[]>("/api/roles"),
  profile: (current_role_id: string, edits?: { canonical_title: string; included: boolean; proficiency_level?: number | null }[]) =>
    request<Profile>("/api/profile", { method: "POST", body: JSON.stringify({ current_role_id, edits }) }),
  profileConversation: (messages: ChatMessage[], resume_text?: string) =>
    request<ProfileConversation>("/api/ai/profile-conversation", { method: "POST", body: JSON.stringify({ messages, resume_text }) }),
  gap: (profile: Profile, target_role_id: string) =>
    request<GapAnalysis>("/api/gap-analysis", { method: "POST", body: JSON.stringify({ profile, target_role_id }) }),
  recommend: (profile: Profile) =>
    request<{ profile_source: ProfileSource; recommendations: Recommendation[] }>("/api/recommend-roles", {
      method: "POST",
      body: JSON.stringify({ profile, top_k: 4, include_market_validation: false })
    }),
  market: (target_role_id: string, location: string, max_jobs: number, use_apify: boolean) =>
    request<Market>("/api/market-validate", { method: "POST", body: JSON.stringify({ target_role_id, location, max_jobs, use_apify }) }),
  plan: (profile: Profile, target_role_id: string) =>
    request<Plan>("/api/learning-plan", { method: "POST", body: JSON.stringify({ profile, target_role_id, include_market_validation: true, duration_days: 30 }) }),
  courses: (target_role_id: string, focus_skills: string[], location = "Singapore") =>
    request<CourseSearch>("/api/course-search", { method: "POST", body: JSON.stringify({ target_role_id, focus_skills, location }) }),
  parseResume: (file: File) =>
    uploadFile<{ text: string; pages: number }>("/api/parse-resume", file),
};
