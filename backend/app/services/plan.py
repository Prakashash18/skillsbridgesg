from app.models.schemas import LearningPlanResponse, WeeklyPlan
from app.services.gap_analysis import analyse_gap
from app.services.market import validate_market

HONESTY_LINE = "Be realistic: 30 days won't fully retrain you for a brand-new career. What it will do is close your biggest skill gaps, give you real proof you can do the work, and help you tell your story to employers."


def build_learning_plan(profile, target_role_id: str, include_market_validation: bool = True) -> LearningPlanResponse:
    gap = analyse_gap(profile, target_role_id)
    market = validate_market(target_role_id) if include_market_validation else None
    focus = [item.skill.canonical_title for item in (gap.missing + gap.proficiency_gaps)[:3]]
    if not focus:
        focus = [item.skill.canonical_title for item in gap.transferable[:2]]
    primary = focus[0] if focus else "target role evidence"
    secondary = focus[1] if len(focus) > 1 else "stakeholder-ready portfolio work"
    weekly = [
        WeeklyPlan(
            week=1,
            theme="Get clear on where you stand",
            tasks=[
                "List what you already do well that this new role also needs.",
                "Look at the role's main tasks and tick the ones you've done before.",
                "Find 8-10 companies hiring for this role and save the job links.",
            ],
        ),
        WeeklyPlan(
            week=2,
            theme=f"Learn the basics of {primary}",
            tasks=[
                f"Take one short online course or video on {primary} (a few hours is enough).",
                f"Write simple notes linking {primary} to work you've already done.",
                f"Try a small practice exercise so you've actually used {primary} yourself.",
            ],
        ),
        WeeklyPlan(
            week=3,
            theme=f"Practise {secondary} on something real",
            tasks=[
                f"Build one small thing that shows you can use {secondary}.",
                "Ask a friend or mentor to look at it and tell you what's unclear.",
                "Prepare 2-3 short interview stories: the situation, what you did, and the result.",
            ],
        ),
        WeeklyPlan(
            week=4,
            theme="Get ready and start applying",
            tasks=[
                "Turn your small project into a simple one-page summary anyone can understand.",
                "Update your resume so it speaks to this new role.",
                "Apply to 5 realistic jobs and keep track of who replies.",
            ],
        ),
    ]
    market_evidence = []
    if market:
        market_evidence = [f"{skill}: {count} sample postings" for skill, count in market.mapped_skill_frequency.items()]
    return LearningPlanResponse(
        target_role=gap.target_role,
        profile_source=profile.profile_source,
        focus_skills=focus,
        weekly_plan=weekly,
        daily_tasks=["Spend 45 minutes learning or practising the skill.", "Write down one example from your past work that proves a skill.", "Update your list of jobs you've applied to."],
        mini_project=f"Build a small, real example of {gap.target_role.role_title} work using {primary} — something you could actually show an employer.",
        final_portfolio_task="Write a short, clear story of one project: what the problem was, what you did, and what changed because of it.",
        dataset_evidence=[f"{item.skill.canonical_title} requires level {item.target_proficiency_level}" for item in (gap.missing + gap.proficiency_gaps)[:5]],
        market_evidence=market_evidence,
        honesty_line=HONESTY_LINE,
    )

