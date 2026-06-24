"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Bot,
  Briefcase,
  CalendarCheck,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Compass,
  Database,
  Download,
  ExternalLink,
  FileText,
  GraduationCap,
  Info,
  Lightbulb,
  Loader2,
  Lock,
  MessagesSquare,
  MoreHorizontal,
  PenLine,
  Search,
  Send,
  Sparkles,
  Target,
  TrendingUp,
  Upload,
  User,
} from "lucide-react";
import { api, ChatMessage, CourseSearch, GapAnalysis, Market, Plan, Profile, ProfileConversation, Recommendation, Role } from "@/lib/api";

type Stage = "intake" | "roles" | "role" | "market" | "plan";

type TransitionState = {
  message: string;
  subMessage: string;
};

const seedMessage =
  "Hi, I'm your SkillBridge AI career assistant. Let's start by understanding your current role, then I'll map it to SkillsFuture roles and skills. What's your job title today, and what do you spend most of your week doing?";

/** The four visible pipeline stages, in order. The "role" detail view lives under Roles. */
const pipeline: { key: Exclude<Stage, "role">; label: string; hint: string; icon: typeof MessagesSquare }[] = [
  { key: "intake", label: "Conversation", hint: "Map your profile", icon: MessagesSquare },
  { key: "roles", label: "Roles", hint: "Compare pathways", icon: Compass },
  { key: "market", label: "Jobs", hint: "Validate demand", icon: Briefcase },
  { key: "plan", label: "Plan", hint: "30-day roadmap", icon: CalendarCheck },
];

function stageIndex(stage: Stage): number {
  if (stage === "intake") return 0;
  if (stage === "roles" || stage === "role") return 1;
  if (stage === "market") return 2;
  return 3;
}

export function SkillBridgeApp() {
  const [stage, setStage] = useState<Stage>("intake");
  const [roles, setRoles] = useState<Role[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: seedMessage }]);
  const [draft, setDraft] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [conversation, setConversation] = useState<ProfileConversation | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [gap, setGap] = useState<GapAnalysis | null>(null);
  const [market, setMarket] = useState<Market | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [courses, setCourses] = useState<CourseSearch | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Loading quarterly SkillsFuture dataset...");
  const [error, setError] = useState<string | null>(null);
  const [transition, setTransition] = useState<TransitionState | null>(null);
  const [resumeParseStatus, setResumeParseStatus] = useState<string | null>(null);

  const skillNames = useMemo(() => (profile?.skills || []).map((skill) => skill.canonical_title), [profile]);

  useEffect(() => {
    async function boot() {
      try {
        const ingest = await api.catalogStatus();
        const loadedRoles = await api.roles();
        setRoles(loadedRoles);
        setStatus(`${ingest.mode === "skillsfuture_workbooks" ? "SkillsFuture dataset" : "Demo dataset"} loaded · ${ingest.counts.roles} roles`);
      } catch (err) {
        setStatus(err instanceof Error ? err.message : "Start FastAPI on port 8000 to load the dataset-backed flow.");
      }
    }
    boot();
  }, []);

  async function sendMessage(content = draft) {
    const clean = content.trim();
    if (!clean && !resumeText.trim()) return;
    const nextMessages = clean ? [...messages, { role: "user" as const, content: clean }] : messages;
    setMessages(nextMessages);
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      const response = await api.profileConversation(nextMessages, resumeText);
      setConversation(response);
      // Always keep the latest AI-inferred profile so the user can choose to
      // explore as soon as skills are mapped — not only when the model flags ready.
      setProfile(response.profile);
      setMessages([...nextMessages, { role: "assistant", content: assistantChatContent(response) }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "The AI profile conversation failed. Please try again.";
      setError(message);
      setMessages([...nextMessages, { role: "assistant", content: `I could not complete the profile mapping yet: ${message}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function exploreRoles() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    setTransition({ message: "Matching your skills to 2,027 SkillsFuture roles…", subMessage: "Scoring overlap across TSC/CCS skill requirements" });
    try {
      const response = await api.recommend(profile);
      setRecommendations(response.recommendations);
      setStage("roles");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Role recommendation failed.");
    } finally {
      setBusy(false);
      setTransition(null);
    }
  }

  async function chooseRole(recommendation: Recommendation) {
    if (!profile) return;
    setSelected(recommendation);
    setBusy(true);
    setError(null);
    setTransition({ message: "Analysing career pathway gaps…", subMessage: "Comparing your profile against this role's TSC requirements" });
    try {
      const response = await api.gap(profile, recommendation.role.role_id);
      setGap(response);
      setStage("role");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gap analysis failed.");
    } finally {
      setBusy(false);
      setTransition(null);
    }
  }

  async function scrapeJobs() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setTransition({ message: "Searching live job openings…", subMessage: "Scraping Singapore jobs via Google · powered by Apify" });
    try {
      const response = await api.market(selected.role.role_id, "Singapore", 8, true);
      setMarket(response);
      setStage("market");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job market validation failed.");
    } finally {
      setBusy(false);
      setTransition(null);
    }
  }

  async function buildPlan() {
    if (!profile || !selected) return;
    setBusy(true);
    setError(null);
    setTransition({ message: "Building your 30-day transition plan…", subMessage: "Finding courses and structuring your weekly roadmap" });
    try {
      const planResponse = await api.plan(profile, selected.role.role_id);
      setPlan(planResponse);
      const focusSkills = planResponse.focus_skills.length ? planResponse.focus_skills : gap?.missing.slice(0, 3).map((item) => item.skill.canonical_title) || [];
      const courseResponse = await api.courses(selected.role.role_id, focusSkills);
      setCourses(courseResponse);
      setStage("plan");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan generation failed.");
    } finally {
      setBusy(false);
      setTransition(null);
    }
  }

  async function handlePdfUpload(file: File) {
    setResumeParseStatus("Parsing PDF…");
    setBusy(true);
    try {
      const result = await api.parseResume(file);
      setResumeText(result.text);
      setResumeParseStatus(`Resume parsed · ${result.pages} page${result.pages !== 1 ? "s" : ""} · sending to AI`);
      await sendMessage(`I've uploaded my resume (${result.pages} page${result.pages !== 1 ? "s" : ""}).`);
    } catch (err) {
      setResumeParseStatus(err instanceof Error ? err.message : "PDF parse failed — please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function reanalyseWithExperience(notes: Record<string, string>) {
    const summary = Object.entries(notes)
      .filter(([, v]) => v.trim())
      .map(([skill, text]) => `${skill}: ${text}`)
      .join("\n");
    if (!summary || !profile || !selected) return;
    setBusy(true);
    setError(null);
    setTransition({ message: "Updating your profile with new experience…", subMessage: "Re-running gap analysis with your additional context" });
    try {
      const updatedMessages = [...messages, { role: "user" as const, content: `Additional experience context:\n${summary}` }];
      const convResponse = await api.profileConversation(updatedMessages, resumeText);
      setConversation(convResponse);
      setProfile(convResponse.profile);
      setMessages([...updatedMessages, { role: "assistant" as const, content: convResponse.assistant_message }]);
      const gapResponse = await api.gap(convResponse.profile, selected.role.role_id);
      setGap(gapResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-analysis failed.");
    } finally {
      setBusy(false);
      setTransition(null);
    }
  }

  const navEnabled = useMemo(
    () => ({
      intake: true,
      roles: recommendations.length > 0,
      role: Boolean(selected && gap),
      market: Boolean(market),
      plan: Boolean(plan),
    }),
    [gap, market, plan, recommendations.length, selected],
  );

  function goTo(nextStage: Stage) {
    if (navEnabled[nextStage]) setStage(nextStage);
  }

  const pipelineNavConfig = useMemo(() => {
    const canExplore = Boolean(conversation?.ready_to_explore || (profile && profile.skills.length >= 2));
    const prev: (() => void) | null =
      stage === "intake" ? null
      : stage === "roles" ? () => setStage("intake")
      : stage === "role" ? () => setStage("roles")
      : stage === "market" ? () => setStage("role")
      : () => setStage(market ? "market" : "role");
    const nextLabel: string | null =
      stage === "intake" ? (canExplore ? "Explore Roles" : null)
      : stage === "roles" ? null
      : stage === "role" ? (market ? "View Jobs" : "Search Jobs")
      : stage === "market" ? (plan ? "View Plan" : "Build Plan")
      : null;
    const nextAction: (() => void) | null =
      stage === "intake" ? (canExplore ? exploreRoles : null)
      : stage === "roles" ? null
      : stage === "role" ? (market ? () => setStage("market") : scrapeJobs)
      : stage === "market" ? (plan ? () => setStage("plan") : buildPlan)
      : null;
    return { prev, nextLabel, nextAction };
  }, [stage, conversation, profile, market, plan]);

  return (
    <main className="min-h-screen pb-20 text-ink">
      {transition ? <LoadingHUD transition={transition} skillNames={skillNames} /> : null}
      <TopBar status={status} />
      <Stepper current={stage} enabled={navEnabled} onStage={goTo} />
      <div className="mx-auto w-full max-w-[1240px] px-4 pb-4 pt-6 md:px-8">
        {error ? (
          <div className="mb-5 flex items-start gap-3 rounded-xl border border-danger/20 bg-dangerSoft px-4 py-3 text-sm font-medium text-danger">
            <span className="mt-0.5">⚠</span>
            <span>{error}</span>
          </div>
        ) : null}
        <div key={stage} className="animate-rise">
          {stage === "intake" ? (
            <Intake
              messages={messages}
              draft={draft}
              conversation={conversation}
              busy={busy}
              status={status}
              roleCount={roles.length}
              onDraft={setDraft}
              onSend={() => sendMessage()}
              onQuickReply={(text) => sendMessage(text)}
              onPdfUpload={handlePdfUpload}
              resumeParseStatus={resumeParseStatus}
              suggestedReplies={conversation?.suggested_replies || []}
              hasConversation={Boolean(conversation)}
              onExplore={exploreRoles}
              aiAnalyzing={busy}
            />
          ) : null}
          {stage === "roles" ? <RoleExplorer profile={profile} recommendations={recommendations} onBack={() => setStage("intake")} onChoose={chooseRole} busy={busy} /> : null}
          {stage === "role" && selected && gap ? <RoleDetail selected={selected} gap={gap} onBack={() => setStage("roles")} onJobs={scrapeJobs} onPlan={buildPlan} busy={busy} onReanalyse={reanalyseWithExperience} /> : null}
          {stage === "market" && selected && market ? <MarketView selected={selected} market={market} onBack={() => setStage("role")} onPlan={buildPlan} busy={busy} onReanalyse={reanalyseWithExperience} /> : null}
          {stage === "plan" && plan ? <PlanView plan={plan} courses={courses} onBack={() => setStage(market ? "market" : "role")} onExploreMore={() => setStage("roles")} /> : null}
        </div>
      </div>
      <PipelineNav
        stage={stage}
        prev={pipelineNavConfig.prev}
        nextLabel={pipelineNavConfig.nextLabel}
        nextAction={pipelineNavConfig.nextAction}
        busy={busy}
      />
    </main>
  );
}

function PipelineNav({
  stage,
  prev,
  nextLabel,
  nextAction,
  busy,
}: {
  stage: Stage;
  prev: (() => void) | null;
  nextLabel: string | null;
  nextAction: (() => void) | null;
  busy: boolean;
}) {
  const stageLabels: Record<Stage, string> = {
    intake: "Conversation",
    roles: "Roles",
    role: "Gap Analysis",
    market: "Jobs",
    plan: "Plan",
  };
  const stageNumbers: Record<Stage, string> = {
    intake: "1 / 4",
    roles: "2 / 4",
    role: "2 / 4",
    market: "3 / 4",
    plan: "4 / 4",
  };
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-4 py-3 md:px-8">
        {/* Back */}
        <button
          disabled={!prev || busy}
          onClick={prev ?? undefined}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-semibold text-body transition enabled:hover:border-brandRing enabled:hover:text-brand disabled:opacity-30"
        >
          <ArrowLeft size={15} /> Back
        </button>

        {/* Stage label */}
        <div className="text-center">
          <div className="text-xs font-bold text-brand">{stageNumbers[stage]}</div>
          <div className="text-sm font-semibold text-ink">{stageLabels[stage]}</div>
        </div>

        {/* Forward */}
        {nextAction && nextLabel ? (
          <button
            disabled={busy}
            onClick={nextAction}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-b from-brand to-brandStrong px-4 py-2 text-sm font-semibold text-white shadow-card transition hover:brightness-110 disabled:opacity-40"
          >
            {nextLabel} <ArrowRight size={15} />
          </button>
        ) : (
          <div className="w-28" />
        )}
      </div>
    </nav>
  );
}

function LoadingHUD({ transition, skillNames }: { transition: TransitionState; skillNames: string[] }) {
  const chips = skillNames.length
    ? skillNames.slice(0, 8)
    : ["Skills Framework", "TSC Analysis", "Career Mapping", "Gap Analysis", "Unique Skills", "CCS Profile"];
  return (
    <div className="animate-overlay fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden" style={{ background: "linear-gradient(160deg, #0a474c 0%, #052a2d 60%, #031e20 100%)" }}>
      {/* Soft radial glow behind rings */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="h-72 w-72 rounded-full opacity-30" style={{ background: "radial-gradient(circle, #16b8aa 0%, transparent 70%)" }} />
      </div>

      {/* Animated rings + logo */}
      <div className="relative flex h-52 w-52 items-center justify-center">
        {/* Outer ping rings */}
        <span className="absolute h-48 w-48 rounded-full border border-brandRing/60" style={{ animation: "hud-ring 2.6s ease-out infinite" }} />
        <span className="absolute h-48 w-48 rounded-full border border-brandRing/60" style={{ animation: "hud-ring 2.6s ease-out infinite 1.2s" }} />
        {/* Spinning dashed ring */}
        <span
          className="absolute h-36 w-36 rounded-full border-2 border-dashed border-brandRing/70"
          style={{ animation: "hud-spin 6s linear infinite" }}
        />
        {/* Counter-spin coral accent ring */}
        <span
          className="absolute h-24 w-24 rounded-full border-2 border-coral/60"
          style={{ animation: "hud-spin-rev 4s linear infinite" }}
        />
        {/* Center logo */}
        <div
          className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brandRing via-brand to-coral shadow-lift"
          style={{ animation: "hud-pulse 2.2s ease-in-out infinite", boxShadow: "0 0 32px rgba(22,184,170,0.5)" }}
        >
          <Sparkles size={26} className="text-white" strokeWidth={2} />
        </div>
      </div>

      {/* Step message */}
      <div className="mt-4 px-8 text-center">
        <p className="text-[22px] font-bold tracking-tight text-white">{transition.message}</p>
        <p className="mt-2 text-sm font-medium text-white/75">{transition.subMessage}</p>
      </div>

      {/* Floating skill chips — solid teal wash, fully readable */}
      <div className="mt-8 flex max-w-xl flex-wrap justify-center gap-2.5 px-8">
        {chips.map((chip, index) => (
          <span
            key={chip}
            className="inline-flex items-center rounded-full border border-brandRing/50 px-3.5 py-1.5 text-xs font-semibold text-white"
            style={{
              background: "rgba(22,184,170,0.18)",
              animation: `hud-chip-in 3.4s ease-in-out infinite`,
              animationDelay: `${index * 0.38}s`,
            }}
          >
            {chip}
          </span>
        ))}
      </div>

      {/* Shimmer progress bar */}
      <div className="absolute inset-x-0 bottom-0 h-[3px] overflow-hidden">
        <div className="hud-bar h-full w-full" />
      </div>
    </div>
  );
}

function TopBar({ status }: { status: string }) {
  return (
    <header className="sticky top-0 z-30 bg-petrol text-white">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-4 py-3 md:px-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brandRing via-brand to-coral text-white shadow-card">
            <Sparkles size={20} strokeWidth={2.2} />
          </div>
          <div className="leading-tight">
            <div className="text-[17px] font-bold tracking-tight text-white">
              SkillBridge <span className="text-brandRing">SG</span>
            </div>
            <div className="text-xs font-medium text-white/65">SkillsFuture career-transition guide</div>
          </div>
        </div>
        <a
          href="https://jobsandskills.skillsfuture.gov.sg/skills-frameworks#download-the-latest-skills-framework-dataset"
          target="_blank"
          rel="noopener noreferrer"
          title="Open the SkillsFuture Skills Framework — the source of all roles, TSCs and skills"
          className="hidden items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3.5 py-1.5 text-xs font-medium text-white/85 transition hover:border-white/40 hover:bg-white/15 sm:flex"
        >
          <Database size={13} className="text-brandRing" />
          {status}
          <span className="mx-0.5 h-3 w-px bg-white/20" />
          <span className="inline-flex items-center gap-1 text-brandRing">SkillsFuture source <ExternalLink size={12} /></span>
        </a>
      </div>
      {/* SkillsFuture-style multi-colour accent rule */}
      <div className="h-1 w-full bg-gradient-to-r from-brandRing via-brand to-coral" />
    </header>
  );
}

function Stepper({ current, enabled, onStage }: { current: Stage; enabled: Record<Stage, boolean>; onStage: (stage: Stage) => void }) {
  const activeIndex = stageIndex(current);
  return (
    <div className="border-b border-line bg-surface">
      <div className="mx-auto max-w-[1240px] px-4 py-4 md:px-8">
        <ol className="flex items-center">
          {pipeline.map((step, index) => {
            const done = index < activeIndex && enabled[step.key];
            const active = index === activeIndex;
            const reachable = enabled[step.key];
            const locked = !reachable && !active;
            const Icon = done ? Check : locked ? Lock : step.icon;
            return (
              <li key={step.key} className="flex flex-1 items-center last:flex-none">
                <button
                  disabled={locked}
                  onClick={() => onStage(step.key)}
                  className={`group flex items-center gap-3 rounded-xl px-2 py-1.5 text-left transition ${locked ? "cursor-not-allowed" : "hover:bg-subtle"}`}
                >
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-sm font-bold transition ${
                      active
                        ? "border-transparent bg-brand text-white shadow-ring"
                        : done
                          ? "border-transparent bg-brand text-white"
                          : reachable
                            ? "border-lineStrong bg-surface text-brand"
                            : "border-line bg-subtle text-faint"
                    }`}
                  >
                    <Icon size={16} strokeWidth={2.4} />
                  </span>
                  <span className="hidden sm:block">
                    <span className={`block text-sm font-semibold leading-4 ${active || done ? "text-ink" : locked ? "text-faint" : "text-body"}`}>{step.label}</span>
                    <span className={`block text-xs leading-4 ${active ? "text-brand" : "text-muted"}`}>{step.hint}</span>
                  </span>
                </button>
                {index < pipeline.length - 1 ? (
                  <span className="mx-2 h-[2px] flex-1 overflow-hidden rounded-full bg-line md:mx-3">
                    <span className={`block h-full rounded-full bg-brand transition-all duration-500 ${index < activeIndex ? "w-full" : "w-0"}`} />
                  </span>
                ) : null}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

function assistantChatContent(response: ProfileConversation) {
  // Keep the bubble succinct — the assistant asks one question; the answer
  // options are surfaced as clickable quick-reply chips, not pasted inline.
  return response.assistant_message;
}

function Intake(props: {
  messages: ChatMessage[];
  draft: string;
  conversation: ProfileConversation | null;
  busy: boolean;
  status: string;
  roleCount: number;
  onDraft: (value: string) => void;
  onSend: () => void;
  onQuickReply: (text: string) => void;
  onPdfUpload: (file: File) => void;
  resumeParseStatus: string | null;
  suggestedReplies: string[];
  hasConversation: boolean;
  onExplore: () => void;
  aiAnalyzing: boolean;
}) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [showLinkedInGuide, setShowLinkedInGuide] = useState(false);
  const starterPrompts = ["I teach programming at ITE", "I manage operations and dashboards", "I run sales and key accounts"];
  const showQuickReplies = props.hasConversation && props.suggestedReplies.length > 0;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [props.messages, props.busy]);

  return (
    <div className="grid gap-4 lg:h-[calc(100dvh-184px)] lg:grid-cols-[minmax(0,1fr)_360px]">
      {/* Chat panel — fills the viewport so messages get the most room */}
      <Card className="flex h-[calc(100dvh-184px)] flex-col overflow-hidden p-0 lg:h-full">
        <div className="flex shrink-0 items-center gap-2.5 border-b border-line px-4 py-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brandSoft text-brand">
            <Bot size={17} />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-bold leading-4 text-ink">SkillBridge AI</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] font-medium text-muted">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brandRing opacity-60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand" />
              </span>
              {props.aiAnalyzing ? "Analyzing…" : "Online · ready"}
            </div>
          </div>
          <OpenAIBadge conversation={props.conversation} />
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          {/* Messages */}
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {props.messages.map((message, index) => (
              <ChatBubble key={`${message.role}-${index}`} message={message} />
            ))}
            {props.busy ? (
              <div className="flex items-center gap-2 text-sm font-medium text-muted">
                <Loader2 className="animate-spin text-brand" size={15} />
                Reading your profile signals…
              </div>
            ) : null}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area — compact: chips scroll in one row, upload inline */}
          <div className="shrink-0 border-t border-line px-3 py-2.5 md:px-4">
            {/* Quick replies / starters — single scrollable row, no wrap */}
            {showQuickReplies ? (
              <div className="mb-2 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {props.suggestedReplies.map((reply) => (
                  <button key={reply} disabled={props.busy} onClick={() => props.onQuickReply(reply)}
                    className="shrink-0 whitespace-nowrap rounded-full border border-brand/20 bg-brandSoft px-3 py-1.5 text-xs font-semibold text-brand transition hover:bg-brand hover:text-white disabled:opacity-50">
                    {reply}
                  </button>
                ))}
              </div>
            ) : (
              <div className="mb-2 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {starterPrompts.map((prompt) => (
                  <button key={prompt} onClick={() => props.onDraft(prompt)}
                    className="shrink-0 whitespace-nowrap rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-body transition hover:border-brandRing hover:text-brand">
                    {prompt}
                  </button>
                ))}
              </div>
            )}

            <div className="flex items-end gap-2 rounded-2xl border border-line bg-subtle p-1.5 transition focus-within:border-brandRing focus-within:bg-surface">
              <input ref={fileInputRef} type="file" accept=".pdf" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) props.onPdfUpload(f); e.target.value = ""; }} />
              <button
                disabled={props.busy}
                onClick={() => fileInputRef.current?.click()}
                title="Upload resume PDF"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted transition hover:bg-brandSoft hover:text-brand disabled:opacity-40"
              >
                <Upload size={17} />
              </button>
              <textarea
                value={props.draft}
                onChange={(e) => props.onDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); props.onSend(); } }}
                placeholder="Type your reply, or tap a chip above…"
                rows={1}
                className="max-h-28 min-h-[36px] flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-6 outline-none placeholder:text-faint"
              />
              <button
                disabled={props.busy}
                onClick={props.onSend}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-b from-brand to-brandStrong text-white shadow-card transition hover:brightness-110 active:scale-95 disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </div>

            {/* Helper row: LinkedIn link + parse status */}
            <div className="mt-1.5 flex items-center gap-2 px-1">
              <button
                onClick={() => setShowLinkedInGuide((v) => !v)}
                className="inline-flex items-center gap-0.5 text-[11px] font-medium text-muted transition hover:text-brand"
              >
                How to export a LinkedIn PDF {showLinkedInGuide ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              </button>
              {props.resumeParseStatus ? (
                <span className={`ml-auto truncate text-[11px] font-medium ${props.resumeParseStatus.includes("fail") || props.resumeParseStatus.includes("error") ? "text-warn" : "text-brand"}`}>
                  {props.resumeParseStatus}
                </span>
              ) : null}
            </div>

            {showLinkedInGuide ? <LinkedInGuide /> : null}
          </div>
        </div>
      </Card>

      {/* Sidebar: discovery panel only */}
      <aside className="lg:h-full lg:min-h-0">
        <DiscoveryPanel className="h-full overflow-y-auto" conversation={props.conversation} status={props.status} roleCount={props.roleCount} onExplore={props.onExplore} aiAnalyzing={props.aiAnalyzing} />
      </aside>
    </div>
  );
}

function OpenAILogo({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071.006l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071-.006l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z" />
    </svg>
  );
}

function OpenAIBadge({ conversation }: { conversation: ProfileConversation | null }) {
  // Fallback flow (no API key) returns mode "mock" — be honest and hide the
  // OpenAI badge. Before the first turn, show the configured model optimistically.
  if (conversation && conversation.mode === "mock") return null;
  const model = (conversation?.model || "gpt-4.1").toUpperCase();
  return (
    <span
      title={`Conversation powered by OpenAI ${model}`}
      className="ml-auto hidden items-center gap-1.5 rounded-full border border-line bg-subtle px-2.5 py-1 text-[11px] font-semibold text-body sm:inline-flex"
    >
      <OpenAILogo className="h-3.5 w-3.5 text-ink" />
      <span className="text-muted">Powered by</span>
      <span className="text-ink">OpenAI {model}</span>
    </span>
  );
}

function ApifyMark({ className = "" }: { className?: string }) {
  // Apify-green hexagon logomark.
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M12 1.5l9.09 5.25v10.5L12 22.5l-9.09-5.25V6.75L12 1.5z" fill="#97CA3F" />
      <path d="M12 6.2l5.02 2.9v5.8L12 17.8l-5.02-2.9V9.1L12 6.2z" fill="#fff" fillOpacity="0.92" />
      <circle cx="12" cy="12" r="1.7" fill="#5b8a1f" />
    </svg>
  );
}

function ApifyBadge({ live }: { live: boolean }) {
  return (
    <span
      title={live ? "Live jobs scraped via Apify Google Jobs" : "Powered by Apify — live scraping resumes when credit is available"}
      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1.5 text-[11px] font-semibold text-body"
    >
      <ApifyMark className="h-3.5 w-3.5" />
      <span className="text-muted">Powered by</span>
      <span className="text-ink">Apify</span>
      {live ? <span className="rounded-full bg-brandSoft px-1.5 py-0.5 text-[10px] font-bold uppercase text-brand">Live</span> : null}
    </span>
  );
}

function LinkedInGuide() {
  const steps = [
    { icon: <User size={16} />, title: "Open your profile", body: "Go to linkedin.com on desktop and click your photo → View Profile." },
    { icon: <MoreHorizontal size={16} />, title: 'Click "More…"', body: 'Under your name on your profile page, click the "More" button in the action bar.' },
    { icon: <Download size={16} />, title: "Save to PDF", body: 'Select "Save to PDF" from the dropdown. Your browser will download a clean PDF.' },
  ];
  return (
    <div className="mt-3 animate-rise rounded-xl border border-brandRing/20 bg-brandSofter p-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-bold text-brand">
        <FileText size={14} /> How to export your LinkedIn profile as PDF
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {steps.map((step, i) => (
          <div key={step.title} className="flex gap-3 rounded-lg border border-line bg-surface p-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-white text-xs font-bold">
              {i + 1}
            </span>
            <div>
              <div className="flex items-center gap-1 text-xs font-bold text-ink">{step.icon} {step.title}</div>
              <p className="mt-1 text-[11px] leading-4 text-muted">{step.body}</p>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] leading-4 text-muted">Then click "Upload resume PDF" above to automatically parse and send it to the AI.</p>
    </div>
  );
}

function DiscoveryPanel({ conversation, status, roleCount, onExplore, aiAnalyzing, className = "" }: { conversation: ProfileConversation | null; status: string; roleCount: number; onExplore: () => void; aiAnalyzing: boolean; className?: string }) {
  const prevConvoRef = useRef(conversation);
  const [flashing, setFlashing] = useState(false);

  useEffect(() => {
    if (conversation && conversation !== prevConvoRef.current) {
      prevConvoRef.current = conversation;
      setFlashing(true);
      const timer = setTimeout(() => setFlashing(false), 1200);
      return () => clearTimeout(timer);
    }
  }, [conversation]);

  if (!conversation) {
    return (
      <Card className={className}>
        <div className="flex items-center justify-between gap-2">
          <SectionLabel icon={<TrendingUp size={15} />}>Live AI insights</SectionLabel>
          {aiAnalyzing ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-brand">
              <span className="animate-dot h-2 w-2 rounded-full bg-brand" />
              Analyzing…
            </span>
          ) : null}
        </div>
        <p className="mt-3 text-sm leading-6 text-muted">Signals, confidence, and next questions appear here as the conversation develops.</p>
        <div className="mt-4 rounded-xl border border-line bg-subtle p-3.5 text-sm text-body">
          <div className="mb-1 flex items-center gap-2 font-semibold text-ink">
            <Database size={15} className="text-brand" /> Backend reference data
          </div>
          {status}
          {roleCount ? <div className="mt-1 text-muted">{roleCount} official roles in the local catalogue.</div> : null}
        </div>
      </Card>
    );
  }

  const confidence = Math.round(conversation.current_role_confidence * 100);
  const skills = conversation.profile.skills.slice(0, 8).map((skill) => skill.canonical_title);
  const canExplore = conversation.ready_to_explore || conversation.profile.skills.length >= 2;
  return (
    <Card className={`${flashing ? "animate-flash" : ""} ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <SectionLabel icon={<Target size={15} />}>Current role discovery</SectionLabel>
          {aiAnalyzing ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-brand">
              <span className="animate-dot h-2 w-2 rounded-full bg-brand" />
              Analyzing…
            </span>
          ) : null}
        </div>
        <Chip tone={conversation.mode === "openai" ? "brand" : "neutral"}>{conversation.mode === "openai" ? "AI live" : "Fallback"}</Chip>
      </div>
      <div className="mt-4 rounded-xl border border-line bg-subtle p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
              {conversation.ready_to_explore ? "Likely role" : "Still learning"}
              <InfoTip title="Why this role?" source={SOURCE.framework}>
                The AI matched your described work to the closest official SkillsFuture job role.
                {conversation.evidence_summary.length ? ` Signals used: ${conversation.evidence_summary.join("; ")}.` : ""}
              </InfoTip>
            </div>
            <div className="mt-0.5 text-lg font-bold leading-6 text-ink">{conversation.ready_to_explore ? conversation.mapped_role.role_title : "Need one more detail"}</div>
            <p className="mt-1 text-sm leading-5 text-muted">
              {conversation.ready_to_explore ? `${conversation.mapped_role.sector} · ${conversation.mapped_role.track}` : "Probing before locking the official mapping."}
            </p>
          </div>
          <div className="flex items-center gap-1 text-right">
            <span className="text-2xl font-bold text-brand">{confidence}%</span>
            <InfoTip title="Role confidence" source={SOURCE.framework}>
              How sure the AI is about this role mapping, based on how clearly your described tasks, tools, and domain align with the role profile. Exploration unlocks at higher confidence.
            </InfoTip>
          </div>
        </div>
        <Progress value={confidence} />
      </div>
      {conversation.evidence_summary.length ? (
        <div className="mt-4">
          <div className="text-xs font-semibold text-muted">Signals heard</div>
          <div className="mt-2 flex flex-wrap gap-1.5">{conversation.evidence_summary.map((item, index) => <Chip key={`${item}-${index}`}>{item}</Chip>)}</div>
        </div>
      ) : null}
      {skills.length ? (
        <div className="mt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted">
            Skills inferred (<Term term="TSC" /> / <Term term="CCS" />)
            <InfoTip title="How skills are inferred" source={SOURCE.unique}>
              The AI reads your conversation and matches what you actually do to official SkillsFuture skills, grounded only in the Unique Skills List. Each skill carries an inferred proficiency level (1–5) used for gap analysis.
            </InfoTip>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">{skills.map((skill, index) => <Chip key={`${skill}-${index}`} tone="brand">{skill}</Chip>)}</div>
        </div>
      ) : null}
      <Button onClick={onExplore} disabled={!canExplore} className="mt-5 w-full" icon={<ArrowRight size={16} />}>
        {conversation.ready_to_explore ? "Explore roles to transition into" : canExplore ? "Explore roles from here" : "Share a little more to explore roles"}
      </Button>
    </Card>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const user = message.role === "user";
  return (
    <div className={`flex items-end gap-2.5 ${user ? "justify-end" : "justify-start"}`}>
      {!user ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brandSoft text-brand">
          <Bot size={15} />
        </div>
      ) : null}
      <div
        className={`max-w-[86%] whitespace-pre-line rounded-2xl px-4 py-3 text-[14.5px] leading-6 md:max-w-[78%] ${
          user ? "rounded-br-md bg-gradient-to-b from-brand to-brandStrong text-white shadow-card" : "rounded-bl-md border border-line bg-surface text-ink shadow-card"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}

function RoleExplorer({ profile, recommendations, onBack, onChoose, busy }: { profile: Profile | null; recommendations: Recommendation[]; onBack: () => void; onChoose: (item: Recommendation) => void; busy: boolean }) {
  const same = recommendations.filter((item) => item.domain_type === "same_domain");
  const cross = recommendations.filter((item) => item.domain_type === "cross_domain");
  const topScore = Math.round((recommendations[0]?.match_score || 0) * 100);
  return (
    <div>
      <PageHeader eyebrow="Step 2 · Roles" title="Roles you could move into" subtitle="Expand a group and browse matches one at a time. Ranked by SkillsFuture skill overlap, TSC gaps, and transition realism." action={<BackButton onClick={onBack} />} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_336px]">
        <div className="space-y-5">
          <CareerIdentity profile={profile} topScore={topScore} />
          <DomainGroup title="Same-domain roles" hint="Closest pathway" items={same.length ? same : recommendations} onChoose={onChoose} busy={busy} defaultOpen />
          <DomainGroup title="Cross-domain roles" hint="Pivot options" items={cross} onChoose={onChoose} busy={busy} />
        </div>
        <InsightsRail
          title="How to read this"
          items={[
            "Open a role to inspect missing TSCs and proficiency gaps.",
            "Same-domain roles are usually faster moves; cross-domain pivots may need a stronger proof project.",
            "After picking a role, scrape job openings to see real tool demand.",
          ]}
        />
      </div>
    </div>
  );
}

function CareerIdentity({ profile, topScore }: { profile: Profile | null; topScore: number }) {
  const skills = profile?.skills.slice(0, 5).map((skill) => skill.canonical_title) || [];
  return (
    <Card className="overflow-hidden border-brand/15 bg-gradient-to-br from-brandSofter via-surface to-brandSoft">
      <div className="grid gap-5 lg:grid-cols-[1fr_220px]">
        <div>
          <SectionLabel icon={<BadgeCheck size={15} />}>Your career identity</SectionLabel>
          <h2 className="mt-2.5 text-2xl font-bold tracking-tight text-ink md:text-[28px]">{profile?.role.role_title || "Working profile"}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
            {profile ? `Mapped from your conversation to ${profile.role.sector} · ${profile.role.track}.` : "Complete the conversation to create your first SkillsFuture-backed profile."}
          </p>
          <div className="mt-4 flex flex-wrap gap-1.5">{skills.map((skill, index) => <Chip key={`${skill}-${index}`}>{skill}</Chip>)}</div>
        </div>
        <div className="flex flex-col justify-center rounded-xl border border-line bg-surface/70 p-4">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
            Opportunity score
            <InfoTip title="How this score is computed" source={SOURCE.framework}>
              The best-matching target role's overlap between your inferred skills and that role's required TSC/CCS skills (weighted by proficiency level). Higher means a shorter, more realistic transition.
            </InfoTip>
          </div>
          <div className="mt-1.5 text-4xl font-bold tracking-tight text-brand">{topScore || 0}<span className="text-xl text-muted">/100</span></div>
          <p className="mt-1.5 text-xs leading-5 text-muted">Transferable skills vs. missing high-priority TSCs.</p>
        </div>
      </div>
    </Card>
  );
}

function DomainGroup({ title, hint, items, onChoose, busy, defaultOpen = false }: { title: string; hint: string; items: Recommendation[]; onChoose: (item: Recommendation) => void; busy: boolean; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [index, setIndex] = useState(0);
  if (!items.length) return null;
  const safeIndex = Math.min(index, items.length - 1);
  const current = items[safeIndex];
  return (
    <Card className="overflow-hidden p-0">
      <button onClick={() => setOpen((value) => !value)} className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-subtle">
        <div className="flex items-center gap-2.5">
          <span className="text-base font-bold text-ink">{title}</span>
          <span className="inline-flex h-6 min-w-[24px] items-center justify-center rounded-full bg-brandSoft px-2 text-xs font-bold text-brand">{items.length}</span>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-muted">
          <span className="hidden sm:inline">{open ? "Collapse" : hint}</span>
          <ChevronDown size={18} className={`transition ${open ? "rotate-180 text-brand" : ""}`} />
        </div>
      </button>
      {open ? (
        <div className="border-t border-line p-5">
          <RoleMatchCard item={current} onChoose={onChoose} busy={busy} />
          {items.length > 1 ? (
            <div className="mt-5 flex items-center justify-between gap-3 border-t border-line pt-4">
              <button
                onClick={() => setIndex(Math.max(0, safeIndex - 1))}
                disabled={safeIndex === 0}
                className="inline-flex items-center gap-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-body transition enabled:hover:border-brandRing enabled:hover:text-brand disabled:opacity-40"
              >
                <ChevronLeft size={15} /> Prev
              </button>
              <div className="flex items-center gap-2.5">
                <div className="flex gap-1.5">
                  {items.map((item, dot) => (
                    <button
                      key={item.role.role_id}
                      onClick={() => setIndex(dot)}
                      aria-label={`Match ${dot + 1}`}
                      className={`h-2 rounded-full transition-all ${dot === safeIndex ? "w-5 bg-brand" : "w-2 bg-lineStrong hover:bg-muted"}`}
                    />
                  ))}
                </div>
                <span className="text-xs font-medium text-muted">{safeIndex + 1} of {items.length}</span>
              </div>
              <button
                onClick={() => setIndex(Math.min(items.length - 1, safeIndex + 1))}
                disabled={safeIndex === items.length - 1}
                className="inline-flex items-center gap-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-body transition enabled:hover:border-brandRing enabled:hover:text-brand disabled:opacity-40"
              >
                Next <ChevronRight size={15} />
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function RoleMatchCard({ item, onChoose, busy }: { item: Recommendation; onChoose: (item: Recommendation) => void; busy: boolean }) {
  return (
    <div className="animate-rise" key={item.role.role_id}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold leading-6 text-ink">{item.role.role_title}</h3>
          <p className="mt-1 text-xs font-medium text-muted">{item.role.sector} · {item.role.track}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <MatchChip value={Math.round(item.match_score * 100)} />
          <InfoTip title="Why this role & match" source={SOURCE.framework}>
            {item.ai_rationale || item.tier_note} The match score reflects overlap between your inferred skills and this role's required TSC/CCS skills; tier "{item.tier}" reflects how big the jump is.
          </InfoTip>
        </div>
      </div>
      <p className="mt-3 text-sm leading-6 text-body">{item.ai_rationale || item.tier_note}</p>
      {item.required_skills?.length ? (
        <div className="mt-4">
          <div className="mb-1.5 text-xs font-semibold text-muted">Likely required</div>
          <div className="flex flex-wrap gap-1.5">{item.required_skills.slice(0, 6).map((skill, index) => <Chip key={`${item.role.role_id}-req-${skill}-${index}`}>{skill}</Chip>)}</div>
        </div>
      ) : null}
      <div className="mt-4">
        <div className="mb-1.5 text-xs font-semibold text-muted">Practical gaps</div>
        <div className="flex flex-wrap gap-1.5">
          {(item.practical_gap_skills?.length ? item.practical_gap_skills.map((gap) => gap.skill) : item.top_missing_skills.map((skill) => skill.canonical_title)).slice(0, 5).map((skill, index) => (
            <Chip key={`${item.role.role_id}-gap-${skill}-${index}`} tone="warn">{skill}</Chip>
          ))}
        </div>
      </div>
      <Button onClick={() => onChoose(item)} disabled={busy} className="mt-5 w-full" icon={<ArrowRight size={16} />}>
        Explore career pathway
      </Button>
    </div>
  );
}

type GapRow = {
  title: string;
  level?: number | null;
  type: "TSC" | "CCS";
  isEmerging?: boolean;
  isCasl?: boolean;
  why?: string;
  signal?: string | null;
  source?: "conversation" | "catalog" | "jobs";
};

function buildGapRows(gap: GapAnalysis): GapRow[] {
  // The AI "practical gaps" and the catalog "missing" list are largely the same
  // skills shown twice. Merge them into one deduped list so the user sees each
  // skill once, with the richest available context.
  const byTitle = new Map<string, GapRow>();
  for (const item of gap.missing) {
    byTitle.set(item.skill.canonical_title, {
      title: item.skill.canonical_title,
      level: item.target_proficiency_level,
      type: item.skill.skill_type,
      isEmerging: item.skill.is_emerging,
      isCasl: item.skill.is_casl,
    });
  }
  for (const practical of gap.practical_gap_skills || []) {
    const existing = byTitle.get(practical.skill) || { title: practical.skill, type: "TSC" as const };
    existing.why = practical.why_required;
    existing.signal = practical.current_signal;
    existing.source = practical.evidence_source;
    byTitle.set(practical.skill, existing);
  }
  return Array.from(byTitle.values());
}

function RoleDetail({ selected, gap, onBack, onJobs, onPlan, busy, onReanalyse }: { selected: Recommendation; gap: GapAnalysis; onBack: () => void; onJobs: () => void; onPlan: () => void; busy: boolean; onReanalyse: (notes: Record<string, string>) => void }) {
  const match = Math.round(gap.match_score * 100);
  const rows = useMemo(() => buildGapRows(gap), [gap]);
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const addedCount = Object.values(evidence).filter((value) => value.trim()).length;
  const setSkillEvidence = (title: string, text: string) => setEvidence((prev) => ({ ...prev, [title]: text }));

  return (
    <div>
      <PageHeader eyebrow="Step 2 · Gap analysis" title={selected.role.role_title} subtitle="What you'd need to build to move into this role — one skill at a time." action={<BackButton onClick={onBack} />} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_336px]">
        <div className="space-y-5">
          {/* Readiness summary — donut + collapsible AI explanation */}
          <Card>
            <div className="grid gap-5 md:grid-cols-[160px_1fr] md:items-center">
              <Donut value={match} label="Match" />
              <div>
                <div className="flex items-center gap-1.5">
                  <h2 className="text-lg font-bold text-ink">Transition readiness</h2>
                  <InfoTip title="How the match is computed" source={SOURCE.framework}>
                    Your inferred skills are compared against this role's official required TSC/CCS skills and proficiency levels. The donut shows direct matches; weighted overlap credits partial proficiency. The checklist below is the skills this role needs that you haven't shown yet.
                  </InfoTip>
                </div>
                <CollapsibleText text={gap.ai_summary || `You have a ${match}% direct skill match. The skills below are your best targets for a short proof project and course plan.`} />
                <div className="mt-4 flex flex-wrap gap-1.5">
                  <TierBadge tier={selected.tier} />
                  <Chip>{Math.round(gap.weighted_overlap * 100)}% weighted overlap</Chip>
                  {gap.analysis_mode ? <Chip tone={gap.analysis_mode === "openai_catalog" ? "brand" : "neutral"}>{gap.analysis_mode === "openai_catalog" ? "AI + catalog" : "Fallback"}</Chip> : null}
                </div>
              </div>
            </div>
          </Card>

          {/* Scaffolded skill checklist */}
          {rows.length ? (
            <Card className="overflow-hidden p-0">
              <div className="border-b border-line px-5 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-1.5">
                    <SectionLabel icon={<Target size={15} />}>Skills to build ({rows.length})</SectionLabel>
                    <InfoTip title="Where each skill comes from" source={SOURCE.framework}>
                      These are the skills this role needs that you haven't evidenced yet. Tap <b>Why?</b> to see why it matters, or <b>I have this</b> to add a project or certificate — then update your match.
                    </InfoTip>
                  </div>
                  {addedCount > 0 ? <Chip tone="brand">{addedCount} marked</Chip> : null}
                </div>
                <p className="mt-1.5 text-xs leading-5 text-muted">Already have one? Tap "I have this" and add a project or cert — we'll re-score your match.</p>
              </div>
              <div className="divide-y divide-line">
                {rows.map((row, index) => (
                  <GapSkillCard key={row.title} row={row} index={index} evidenceText={evidence[row.title] || ""} onEvidence={setSkillEvidence} />
                ))}
              </div>
              {addedCount > 0 ? (
                <div className="border-t border-line bg-brandSofter px-5 py-4">
                  <Button onClick={() => onReanalyse(evidence)} disabled={busy} className="w-full" icon={<Sparkles size={16} />}>
                    Update my match with {addedCount} skill{addedCount !== 1 ? "s" : ""} I have
                  </Button>
                </div>
              ) : null}
            </Card>
          ) : null}

          {/* Depth gaps only when present */}
          {gap.proficiency_gaps?.length ? (
            <Card>
              <SectionLabel icon={<TrendingUp size={15} />}>Skills needing more depth ({gap.proficiency_gaps.length})</SectionLabel>
              <div className="mt-3 space-y-2">
                {gap.proficiency_gaps.map((item, index) => (
                  <div key={`${item.skill.canonical_title}-${index}`} className="flex items-center justify-between gap-3 rounded-lg border border-line bg-subtle px-3.5 py-2.5">
                    <span className="text-sm font-semibold text-ink">{item.skill.canonical_title}</span>
                    <span className="shrink-0 text-xs font-medium text-muted">level {item.current_proficiency_level ?? "-"} → {item.target_proficiency_level ?? "-"}</span>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <Button onClick={onJobs} disabled={busy} icon={<Search size={16} />}>
              Scrape job openings
            </Button>
            <Button onClick={onPlan} disabled={busy} variant="secondary">
              Skip to 30-day plan
            </Button>
          </div>
        </div>
        <InsightsRail
          title="What to do here"
          items={[
            `This role needs ${rows.length} skill${rows.length !== 1 ? "s" : ""} you haven't shown yet.`,
            "Tap a skill to see why it matters, or mark the ones you already have.",
            "Adding a project or cert re-scores your match instantly.",
            "Next, check whether employers actually ask for these in real jobs.",
          ]}
        />
      </div>
    </div>
  );
}

function CollapsibleText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 170;
  return (
    <div className="mt-2">
      <p className={`text-sm leading-6 text-body ${!open && long ? "line-clamp-2" : ""}`}>{text}</p>
      {long ? (
        <button onClick={() => setOpen((value) => !value)} className="mt-1 text-xs font-semibold text-brand hover:text-brandStrong">
          {open ? "Show less" : "Read more"}
        </button>
      ) : null}
    </div>
  );
}

function GapSkillCard({ row, index, evidenceText, onEvidence }: { row: GapRow; index: number; evidenceText: string; onEvidence: (title: string, text: string) => void }) {
  const [showWhy, setShowWhy] = useState(false);
  const [adding, setAdding] = useState(false);
  const has = Boolean(evidenceText.trim());
  const sourceLabel = row.source ? { conversation: "your chat", catalog: "the role profile", jobs: "job postings" }[row.source] : null;
  return (
    <div className={`transition ${has ? "bg-brandSofter" : ""}`}>
      <div className="flex items-start justify-between gap-3 px-5 py-3.5">
        <div className="flex min-w-0 items-start gap-3">
          <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${has ? "bg-brand text-white" : "bg-subtle text-muted"}`}>
            {has ? <Check size={13} /> : index + 1}
          </span>
          <div className="min-w-0">
            <div className="text-sm font-bold text-ink">{row.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {row.level ? <Chip>Level {row.level}</Chip> : null}
              <Chip><Term term={row.type} /></Chip>
              {row.isEmerging ? <Chip tone="violet"><Term term="Emerging" /></Chip> : null}
              {sourceLabel ? <span className="text-[11px] text-muted">· flagged by {sourceLabel}</span> : null}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {row.why ? (
            <button onClick={() => setShowWhy((value) => !value)} className="rounded-lg px-2 py-1 text-xs font-semibold text-muted transition hover:text-brand">
              {showWhy ? "Hide" : "Why?"}
            </button>
          ) : null}
          <button
            onClick={() => setAdding((value) => !value)}
            className={`rounded-lg border px-2.5 py-1 text-xs font-semibold transition ${has ? "border-brand bg-brand text-white" : "border-line text-brand hover:border-brandRing"}`}
          >
            {has ? "Edit" : "I have this"}
          </button>
        </div>
      </div>
      {showWhy && row.why ? (
        <div className="px-5 pb-3.5 pl-14 text-xs leading-5 text-body">
          {row.why}
          {row.signal ? <p className="mt-1 text-muted">Right now: {row.signal}</p> : null}
        </div>
      ) : null}
      {adding ? (
        <div className="px-5 pb-4 pl-14">
          <textarea
            value={evidenceText}
            onChange={(event) => onEvidence(row.title, event.target.value)}
            placeholder={`Add a project, certificate, or example that shows ${row.title}…`}
            rows={2}
            className="w-full resize-none rounded-lg border border-line bg-surface p-2.5 text-sm leading-6 outline-none transition placeholder:text-faint focus:border-brandRing"
          />
          <button onClick={() => setAdding(false)} className="mt-1.5 text-xs font-semibold text-brand hover:text-brandStrong">Save ✓</button>
        </div>
      ) : null}
    </div>
  );
}

function MarketView({ selected, market, onBack, onPlan, busy, onReanalyse }: { selected: Recommendation; market: Market; onBack: () => void; onPlan: () => void; busy: boolean; onReanalyse: (notes: Record<string, string>) => void }) {
  const [expandedJob, setExpandedJob] = useState<number | null>(null);
  const [experienceNotes, setExperienceNotes] = useState<Record<string, string>>({});
  const [openSkillInput, setOpenSkillInput] = useState<string | null>(null);
  const chartData = Object.entries({ ...market.mapped_skill_frequency, ...market.raw_tool_frequency }).map(([name, value]) => ({ name, value }));
  const allSkills = Array.from(new Set(market.jobs.flatMap((j) => j.extracted_skills))).slice(0, 12);
  const notedCount = Object.values(experienceNotes).filter((v) => v.trim()).length;

  return (
    <div>
      <PageHeader
        eyebrow="Step 3 · Jobs"
        title="Job openings & skill demand"
        subtitle={`Live openings and real employer demand for ${selected.role.role_title}.`}
        action={
          <div className="flex items-center gap-2">
            <ApifyBadge live={market.mode === "apify"} />
            <BackButton onClick={onBack} />
          </div>
        }
      />
      {market.notice ? (
        <div className={`mb-4 flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm font-medium ${market.mode === "apify" ? "border-brand/25 bg-brandSoft text-brand" : "border-amber-300/60 bg-amber-50 text-amber-700"}`}>
          {market.mode === "apify" ? (
            <span className="mt-0.5 inline-flex shrink-0 items-center gap-1.5 rounded-full bg-coral px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-white">
              <span className="h-1.5 w-1.5 rounded-full bg-white" /> Live
            </span>
          ) : (
            <ApifyMark className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          {market.notice}
        </div>
      ) : null}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          {/* Collapsible job list */}
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-line">
              <SectionLabel icon={<Briefcase size={15} />}>
                {market.jobs.length} openings · {market.mode === "apify" ? "live" : "sample"}
              </SectionLabel>
            </div>
            <div className="divide-y divide-line">
              {market.jobs.map((job, index) => (
                <div key={`${job.company}-${job.title}-${index}`}>
                  <button
                    onClick={() => setExpandedJob(expandedJob === index ? null : index)}
                    className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-subtle"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-bold text-ink">{job.title}</div>
                      <div className="mt-0.5 text-xs font-medium text-muted">{job.company} · {job.location}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <MatchChip value={Math.min(98, 70 + job.extracted_skills.length * 4)} />
                      <ChevronDown size={16} className={`text-muted transition ${expandedJob === index ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  {expandedJob === index ? (
                    <div className="animate-rise border-t border-line bg-subtle px-5 pb-5 pt-4">
                      <p className="max-w-3xl whitespace-pre-line text-sm leading-6 text-body">{job.summary}</p>
                      {job.url ? (
                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:text-brandStrong">
                          View &amp; apply <ExternalLink size={14} />
                        </a>
                      ) : null}
                      {job.extracted_skills.length ? (
                        <div className="mt-4">
                          <div className="mb-1.5 text-xs font-semibold text-muted">Skills mentioned</div>
                          <div className="flex flex-wrap gap-1.5">{job.extracted_skills.map((skill, si) => <Chip key={`${job.company}-${skill}-${si}`}>{skill}</Chip>)}</div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>

          {/* Skill annotation panel */}
          <Card>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-1.5">
                <SectionLabel icon={<PenLine size={15} />}>Add your experience</SectionLabel>
                <InfoTip title="Why add experience?" source={SOURCE.framework}>
                  Tell the AI about work you've already done with these skills. It re-runs the gap analysis, updating your match score and closing gaps you've evidenced.
                </InfoTip>
              </div>
              {notedCount > 0 ? <Chip tone="brand">{notedCount} added</Chip> : null}
            </div>
            <p className="mt-2 text-xs leading-5 text-muted">Tap any skill to describe your hands-on experience. Then hit "Update my match" to re-score your profile.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {allSkills.map((skill) => {
                const hasNote = Boolean(experienceNotes[skill]?.trim());
                return (
                  <button
                    key={skill}
                    onClick={() => setOpenSkillInput(openSkillInput === skill ? null : skill)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${hasNote ? "border-brand/30 bg-brand text-white" : "border-line bg-surface text-body hover:border-brandRing hover:text-brand"}`}
                  >
                    {hasNote ? <Check size={11} /> : <PenLine size={11} />}
                    {skill}
                  </button>
                );
              })}
            </div>
            {openSkillInput ? (
              <div className="mt-4 animate-rise rounded-xl border border-brandRing/30 bg-brandSofter p-3.5">
                <div className="mb-2 text-xs font-bold text-ink">Your experience with: {openSkillInput}</div>
                <textarea
                  value={experienceNotes[openSkillInput] || ""}
                  onChange={(e) => setExperienceNotes((prev) => ({ ...prev, [openSkillInput]: e.target.value }))}
                  placeholder="e.g. Built 3 Power BI dashboards for 50k-row sales data at my current role…"
                  className="w-full resize-none rounded-lg border border-line bg-surface p-3 text-sm leading-6 outline-none transition placeholder:text-faint focus:border-brandRing"
                  rows={3}
                />
                <button onClick={() => setOpenSkillInput(null)} className="mt-2 text-xs font-semibold text-brand hover:text-brandStrong">Save ✓</button>
              </div>
            ) : null}
            {notedCount > 0 ? (
              <Button
                onClick={() => onReanalyse(experienceNotes)}
                disabled={busy}
                className="mt-4 w-full"
                icon={<Sparkles size={16} />}
              >
                Update my match with {notedCount} experience{notedCount !== 1 ? "s" : ""}
              </Button>
            ) : null}
          </Card>

          <Button onClick={onPlan} disabled={busy} icon={<ArrowRight size={16} />}>
            Find courses and build 30-day plan
          </Button>
        </div>

        {/* Sidebar */}
        <aside className="space-y-5">
          <Card>
            <div className="flex items-center gap-1.5">
              <SectionLabel icon={<TrendingUp size={15} />}>Skill demand</SectionLabel>
              <InfoTip title="How demand is measured" source={market.mode === "apify" ? SOURCE.jobsLive : SOURCE.jobsDemo}>
                Each bar counts how many postings mention a skill after mapping raw tools to SkillsFuture skills.{" "}
                {market.mode === "apify" ? "Live Google Jobs via Apify." : "Sample postings — live scrape returned nothing."}
              </InfoTip>
            </div>
            <MarketChart data={chartData} />
          </Card>
          {market.practical_skill_insights.length ? (
            <Card>
              <h2 className="text-sm font-bold text-ink">Demand signals</h2>
              <div className="mt-3 space-y-2.5">
                {market.practical_skill_insights.slice(0, 5).map((item, index) => (
                  <div key={`${item.skill}-${index}`} className="rounded-xl border border-line bg-subtle px-3.5 py-3">
                    <div className="text-sm font-semibold text-ink">{item.skill}</div>
                    <div className="mt-0.5 text-xs leading-5 text-muted">{item.note}</div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function PlanView({ plan, courses, onBack, onExploreMore }: { plan: Plan; courses: CourseSearch | null; onBack: () => void; onExploreMore: () => void }) {
  return (
    <div>
      <PageHeader eyebrow="Step 4 · Plan" title="Your courses and 30-day plan" subtitle="A simple week-by-week plan with real things to do, plus courses matched to the skills you need." action={<BackButton onClick={onBack} />} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Card className="border-brand/15 bg-gradient-to-br from-brandSofter via-surface to-brandSoft">
            <div className="grid gap-5 md:grid-cols-[140px_1fr] md:items-center">
              <Donut value={30} label="day plan" rawLabel />
              <div>
                <h2 className="text-lg font-bold text-ink">{plan.target_role.role_title} transition</h2>
                <p className="mt-2 text-sm leading-6 text-body">{plan.honesty_line}</p>
                <div className="mt-3 flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-muted">Focus skills</span>
                  <InfoTip title="Why these focus skills" source={SOURCE.framework}>
                    Chosen from your highest-priority gaps for this role — the missing or under-proficient TSC/CCS skills, prioritised by proficiency gap and how often they appear across roles and in job postings.
                  </InfoTip>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">{plan.focus_skills.map((skill, index) => <Chip key={`${skill}-${index}`} tone="brand">{skill}</Chip>)}</div>
              </div>
            </div>
          </Card>
          <Card>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-base font-bold text-ink">Weekly roadmap</h2>
              <button onClick={onExploreMore} className="text-sm font-semibold text-brand hover:text-brandStrong">Explore other roles</button>
            </div>
            <div className="relative space-y-4 before:absolute before:bottom-4 before:left-[15px] before:top-4 before:w-px before:bg-line">
              {plan.weekly_plan.map((week) => (
                <div key={week.week} className="relative grid gap-3 pl-11">
                  <span className="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border border-line bg-surface text-sm font-bold text-brand">
                    {week.week}
                  </span>
                  <div className="rounded-xl border border-line bg-subtle p-4">
                    <h3 className="text-sm font-bold text-ink">Week {week.week} · {week.theme}</h3>
                    <ul className="mt-2.5 space-y-1.5 text-sm leading-6 text-body">
                      {week.tasks.map((task, index) => (
                        <li key={`${week.week}-${task}-${index}`} className="flex gap-2">
                          <Check className="mt-1 shrink-0 text-brand" size={14} />
                          {task}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
        <aside className="space-y-5">
          <Card>
            <div className="flex items-center gap-1.5">
              <SectionLabel icon={<GraduationCap size={15} />}>Recommended courses</SectionLabel>
              <InfoTip title="Where courses come from" source={courses?.mode === "openai_web_search" ? SOURCE.web : SOURCE.framework}>
                {courses?.mode === "openai_web_search"
                  ? "Found via live web search for Singapore-relevant courses matching your focus skills. Verify provider links before enrolling."
                  : "Demo starting points for SkillsFuture-funded courses. Add an API key for live web-searched recommendations."}
              </InfoTip>
            </div>
            {courses?.notice ? <p className="mt-2 text-xs leading-5 text-muted">{courses.notice}</p> : null}
            <div className="mt-3 space-y-2.5">
              {courses?.courses.map((course, index) => (
                <a key={`${course.title}-${course.url}-${index}`} href={course.url} target="_blank" className="block rounded-xl border border-line bg-surface p-3.5 transition hover:border-brandRing hover:shadow-card">
                  <div className="text-sm font-bold text-ink">{course.title}</div>
                  <div className="mt-0.5 text-xs font-medium text-muted">{course.provider}</div>
                  <p className="mt-1.5 text-xs leading-5 text-body">{course.reason}</p>
                </a>
              ))}
            </div>
          </Card>
          <Card className="bg-brandSofter">
            <SectionLabel icon={<Lightbulb size={15} />}>AI mentor tip</SectionLabel>
            <p className="mt-3 text-sm leading-6 text-body">Make one small thing each week that you can show people. By the end, aim for proof you can do the work — not just a list of courses you finished.</p>
          </Card>
          <Card>
            <h2 className="text-sm font-bold text-ink">Mini project</h2>
            <p className="mt-1.5 text-sm leading-6 text-body">{plan.mini_project}</p>
          </Card>
          <Card>
            <h2 className="text-sm font-bold text-ink">Portfolio task</h2>
            <p className="mt-1.5 text-sm leading-6 text-body">{plan.final_portfolio_task}</p>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function MarketChart({ data }: { data: { name: string; value: number }[] }) {
  const max = Math.max(...data.map((item) => item.value), 1);
  return (
    <div className="mt-4 space-y-2.5">
      {data.slice(0, 8).map((item, index) => (
        <div key={`${item.name}-${index}`}>
          <div className="mb-1 flex items-center justify-between gap-3 text-xs">
            <span className="font-medium text-body">{item.name}</span>
            <span className="font-bold text-brand">{item.value}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-subtle">
            <div className="h-full rounded-full bg-gradient-to-r from-brand to-brandRing" style={{ width: `${Math.max(10, (item.value / max) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function PageHeader({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: React.ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-brand">{eyebrow}</div>
        <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-ink md:text-[32px] md:leading-tight">{title}</h1>
        <p className="mt-1.5 max-w-3xl text-sm leading-6 text-muted">{subtitle}</p>
      </div>
      {action}
    </header>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-line bg-surface px-3.5 py-2 text-sm font-semibold text-body transition hover:border-brandRing hover:text-brand">
      <ArrowLeft size={15} /> Back
    </button>
  );
}

function InsightsRail({ title, items }: { title: string; items: string[] }) {
  return (
    <aside className="space-y-5">
      <Card>
        <SectionLabel icon={<Lightbulb size={15} />}>{title}</SectionLabel>
        <div className="mt-3 space-y-2.5">
          {items.map((item, index) => (
            <div key={`${item}-${index}`} className="flex gap-2.5 rounded-xl border border-line bg-subtle p-3 text-sm leading-6 text-body">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
              {item}
            </div>
          ))}
        </div>
      </Card>
      <Card className="bg-brandSofter">
        <SectionLabel icon={<Database size={15} />}>Dataset note</SectionLabel>
        <p className="mt-2.5 text-sm leading-6 text-muted">SkillsFuture reference data stays in the backend and refreshes quarterly — no user uploads needed.</p>
      </Card>
    </aside>
  );
}

/** Ground-truth data sources every decision is traced back to. */
const SOURCE = {
  framework: "SkillsFuture Skills Framework workbook — job-role TSC/CCS profiles & proficiency levels",
  unique: "SkillsFuture Unique Skills List + TSC→Unique mapping workbooks",
  jobsLive: "Live Google Jobs postings scraped via Apify",
  jobsDemo: "Sample job postings (demo mode — live Apify scrape returned nothing)",
  web: "OpenAI web search",
} as const;

function InfoTip({ title, source, children }: { title: string; source?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [align, setAlign] = useState<"left" | "center" | "right">("center");
  const ref = useRef<HTMLButtonElement | null>(null);

  function toggle(event: React.MouseEvent) {
    event.stopPropagation();
    const rect = ref.current?.getBoundingClientRect();
    if (rect) {
      const margin = 160; // half the popover width
      if (rect.left < margin) setAlign("left");
      else if (window.innerWidth - rect.right < margin) setAlign("right");
      else setAlign("center");
    }
    setOpen((value) => !value);
  }

  const position = align === "left" ? "left-0" : align === "right" ? "right-0" : "left-1/2 -translate-x-1/2";
  return (
    <span className="relative inline-flex align-middle">
      <button
        ref={ref}
        type="button"
        aria-label={`Why: ${title}`}
        onClick={toggle}
        className={`inline-flex h-5 w-5 items-center justify-center rounded-full border transition ${open ? "border-brand bg-brand text-white" : "border-line bg-surface text-muted hover:border-brandRing hover:text-brand"}`}
      >
        <Info size={12} strokeWidth={2.4} />
      </button>
      {open ? (
        <>
          <button type="button" aria-hidden tabIndex={-1} className="fixed inset-0 z-40 cursor-default" onClick={() => setOpen(false)} />
          <span className={`absolute top-7 z-50 w-[min(18rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-3.5 text-left shadow-lift ${position}`}>
            <span className="flex items-center gap-1.5 text-xs font-bold text-ink">
              <Info size={13} className="text-brand" /> {title}
            </span>
            <span className="mt-1.5 block text-xs leading-5 text-body">{children}</span>
            {source ? (
              <span className="mt-2.5 flex items-start gap-1.5 border-t border-line pt-2 text-[11px] leading-4 text-muted">
                <Database size={12} className="mt-0.5 shrink-0 text-brand" />
                <span>Ground truth: {source}</span>
              </span>
            ) : null}
          </span>
        </>
      ) : null}
    </span>
  );
}

/** Plain-language definitions for SkillsFuture jargon, shown on hover. */
const GLOSSARY: Record<string, string> = {
  TSC: "Technical Skills & Competencies — job-specific technical skills defined in the SkillsFuture Skills Framework (e.g. Data Analytics, SQL).",
  CCS: "Critical Core Skills — transferable workplace skills (e.g. Communication, Stakeholder Management) that apply across most jobs.",
  "Unique Skills": "SkillsFuture's de-duplicated master list that maps many overlapping role-specific TSCs to one canonical skill.",
  CASL: "Critical & Adaptable Skills List — skills flagged as especially important and transferable across Singapore's economy.",
  Emerging: "A skill the Skills Framework flags as rising in demand for future-ready roles.",
};

function Term({ term, label }: { term: string; label?: React.ReactNode }) {
  const def = GLOSSARY[term];
  if (!def) return <>{label ?? term}</>;
  return (
    <span className="group relative inline-flex cursor-help items-center">
      <span className="underline decoration-dotted underline-offset-2">{label ?? term}</span>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-60 -translate-x-1/2 rounded-lg border border-ink/10 bg-ink p-2.5 text-left text-[11px] font-normal leading-4 text-white opacity-0 shadow-lift transition-opacity duration-150 group-hover:opacity-100"
      >
        <span className="font-bold">{term}</span> — {def}
      </span>
    </span>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-line bg-surface p-5 shadow-card ${className}`}>{children}</div>;
}

function SectionLabel({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm font-bold text-ink">
      <span className="text-brand">{icon}</span>
      {children}
    </div>
  );
}

function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  icon,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary";
  icon?: React.ReactNode;
  className?: string;
}) {
  const base = "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition active:scale-[0.98] disabled:cursor-not-allowed";
  const styles =
    variant === "primary"
      ? "bg-gradient-to-b from-brand to-brandStrong text-white shadow-card hover:brightness-110 disabled:opacity-40"
      : "border border-line bg-surface text-body hover:border-brandRing hover:text-brand disabled:opacity-50";
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${styles} ${className}`}>
      {children}
      {icon}
    </button>
  );
}

function Progress({ value }: { value: number }) {
  return (
    <div className="mt-3.5 h-2 overflow-hidden rounded-full bg-line">
      <div className="h-full rounded-full bg-gradient-to-r from-brand to-brandRing transition-all duration-500" style={{ width: `${Math.max(4, Math.min(100, value))}%` }} />
    </div>
  );
}

function Donut({ value, label, rawLabel = false }: { value: number; label: string; rawLabel?: boolean }) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div className="relative mx-auto h-32 w-32 rounded-full" style={{ background: `conic-gradient(#0f766e ${bounded}%, #eaeff5 0)` }}>
      <div className="absolute inset-[10px] flex flex-col items-center justify-center rounded-full bg-surface text-center shadow-inner">
        <div className="text-2xl font-bold tracking-tight text-brand">{rawLabel ? bounded : `${bounded}%`}</div>
        <div className="text-[11px] font-medium text-muted">{label}</div>
      </div>
    </div>
  );
}

function Chip({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "brand" | "warn" | "violet" }) {
  const tones = {
    neutral: "bg-subtle text-body border-line",
    brand: "bg-brandSoft text-brand border-brand/15",
    warn: "bg-warnSoft text-warn border-warn/15",
    violet: "bg-violetSoft text-violet border-violet/15",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

function MatchChip({ value }: { value: number }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-brandSoft px-2.5 py-1 text-xs font-bold text-brand">
      <span className="h-1.5 w-1.5 rounded-full bg-brand" />
      {value}% match
    </span>
  );
}

function TierBadge({ tier }: { tier: "Adjacent" | "Stretch" | "Pivot" }) {
  const tone = tier === "Adjacent" ? "brand" : tier === "Stretch" ? "violet" : "warn";
  return <Chip tone={tone as "brand" | "violet" | "warn"}>{tier}</Chip>;
}
