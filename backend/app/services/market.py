import os
from collections import Counter

import httpx
from rapidfuzz import fuzz, process

from app.data.db import connect
from app.data.repository import get_role, get_role_skills
from app.models.schemas import JobPosting, MarketBucket, MarketResponse, PracticalSkillInsight
from app.services.normalize import comparison_key

DEFAULT_APIFY_ACTOR = "orgupdate/google-jobs-scraper"

MOCK_POSTINGS = {
    "data-analyst": [
        JobPosting(title="Data Analyst", company="GovTech partner", location="Singapore", url=None, summary="Build SQL datasets, Power BI dashboards, and explain trends to stakeholders.", extracted_skills=[]),
        JobPosting(title="Business Data Analyst", company="Retail analytics team", location="Singapore", url=None, summary="Use Tableau, Python, SQL, and reporting to support commercial decisions.", extracted_skills=[]),
    ],
    "business-analyst": [
        JobPosting(title="Business Analyst", company="Banking delivery squad", location="Singapore", url=None, summary="Run requirements workshops, process mapping, Jira documentation, and stakeholder management.", extracted_skills=[]),
        JobPosting(title="Digital Business Analyst", company="Healthcare transformation office", location="Singapore", url=None, summary="Business analysis, change management, and solution documentation.", extracted_skills=[]),
    ],
    "product-manager": [
        JobPosting(title="Product Manager", company="B2B SaaS startup", location="Singapore", url=None, summary="Own product strategy, roadmap, user research, analytics, and stakeholder management.", extracted_skills=[]),
        JobPosting(title="Digital Product Manager", company="Financial services", location="Singapore", url=None, summary="Lead experimentation, SQL-backed product discovery, and prioritisation.", extracted_skills=[]),
    ],
    "ai-engineer": [
        JobPosting(title="AI Engineer", company="Applied AI lab", location="Singapore", url=None, summary="Use Python, machine learning, SQL, model evaluation, and MLOps.", extracted_skills=[]),
        JobPosting(title="LLM Application Engineer", company="Enterprise AI team", location="Singapore", url=None, summary="Build LLM applications with Python, data analytics, and deployment pipelines.", extracted_skills=[]),
    ],
    "project-manager": [
        JobPosting(title="Project Manager", company="Digital delivery office", location="Singapore", url=None, summary="Project management, risk management, stakeholder reporting, and change management.", extracted_skills=[]),
        JobPosting(title="Delivery Manager", company="Systems integrator", location="Singapore", url=None, summary="Delivery planning, budget control, RAID management, and communication.", extracted_skills=[]),
    ],
}

RAW_TO_CANDIDATE = {
    "sql": "SQL Querying",
    "power bi": "Data Visualisation",
    "tableau": "Data Visualisation",
    "python": "Python Programming",
    "jira": "Project Management",
    "roadmap": "Product Strategy",
    "llm": "Machine Learning",
    "mlops": "Machine Learning",
}


def validate_market(target_role_id: str, location: str = "Singapore", max_jobs: int = 10, use_apify: bool = False) -> MarketResponse:
    role = get_role(target_role_id)
    mode: str = "demo"
    notice = "Demo mode: using sample job postings."
    postings: list[JobPosting] = []
    if use_apify:
        live, reason = _fetch_apify_jobs(role.role_title, location, max_jobs)
        if live:
            postings = live
            mode = "apify"
            notice = f"Live Google Jobs results via Apify for '{role.role_title}' in {location}."
        elif reason == "credit_exhausted":
            notice = "Apify usage limit reached — the live job-scraping credit is used up, so we're showing sample postings. Live results will return once Apify credit refreshes."
        else:
            notice = "Live job search did not return results just now — showing sample postings instead."
    if not postings:
        postings = MOCK_POSTINGS.get(target_role_id) or _generic_postings(target_role_id, role.role_title, location)
    postings = postings[:max_jobs]
    unique_titles = _unique_titles()
    mapped: Counter[str] = Counter()
    raw_tools: Counter[str] = Counter()
    enriched_jobs: list[JobPosting] = []
    for posting in postings:
        # Apify postings pre-extract from the full description; demo postings extract here.
        extracted = posting.extracted_skills or _mock_extract(posting.summary)
        posting.extracted_skills = extracted
        enriched_jobs.append(posting)
        for raw in extracted:
            mapped_title = _map_raw_skill(raw, unique_titles)
            if mapped_title:
                mapped[mapped_title] += 1
            else:
                raw_tools[raw] += 1
    target_keys = {comparison_key(skill.canonical_title): skill.canonical_title for skill in get_role_skills(target_role_id)}
    hot_threshold = max(mapped.values()) * 0.5 if mapped else 1
    official_hot = [title for title, count in mapped.items() if comparison_key(title) in target_keys and count >= hot_threshold]
    official_low = [title for key, title in target_keys.items() if title not in official_hot]
    market_not_official = [title for title, count in mapped.items() if comparison_key(title) not in target_keys and count >= hot_threshold]
    return MarketResponse(
        target_role=role,
        jobs_analysed=len(postings),
        mode=mode,
        notice=notice,
        jobs=enriched_jobs,
        mapped_skill_frequency=dict(mapped.most_common()),
        raw_tool_frequency=dict(raw_tools.most_common()),
        practical_skill_insights=[
            PracticalSkillInsight(skill=skill, count=count, note=f"{skill} appears in {count} sample posting(s) for this role.")
            for skill, count in (mapped + raw_tools).most_common()
        ],
        buckets=[
            MarketBucket(label="Official + Market Hot", skills=official_hot),
            MarketBucket(label="Official but Low Market Signal", skills=official_low),
            MarketBucket(label="Market Hot but Not Official", skills=market_not_official),
        ],
    )


def _fetch_apify_jobs(role_title: str, location: str, max_jobs: int) -> tuple[list[JobPosting] | None, str | None]:
    """Call the Apify Google Jobs scraper and map results to JobPostings.
    Returns (postings, reason). On failure postings is None and reason explains
    why (e.g. 'credit_exhausted', 'no_token', 'http_error', 'no_results') so the
    caller can show an honest notice and fall back to demo postings."""
    token = os.getenv("APIFY_TOKEN")
    if not token:
        return None, "no_token"
    actor = (os.getenv("APIFY_ACTOR_ID") or DEFAULT_APIFY_ACTOR).strip()
    # Apify REST addresses actors with '~' instead of '/'.
    actor_path = actor.replace("/", "~")
    payload = {
        "countryName": "singapore",
        "locationName": location or "Singapore",
        "includeKeyword": role_title,
        "pagesToFetch": 1,
        "datePosted": "month",
    }
    try:
        with httpx.Client(timeout=240) as client:
            response = client.post(
                f"https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items",
                params={"token": token, "maxItems": max_jobs},
                json=payload,
            )
            # A 402 means the Apify account is out of usage credit for this paid
            # actor — surface that distinctly so the UI can say so plainly.
            if response.status_code == 402:
                print("[apify] credit exhausted (HTTP 402):", response.text[:300])
                return None, "credit_exhausted"
            response.raise_for_status()
            items = response.json()
    except Exception as exc:
        print("[apify] request failed:", type(exc).__name__, str(exc)[:300])
        return None, "http_error"
    if not isinstance(items, list):
        return None, "http_error"
    postings: list[JobPosting] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # The actor returns snake_case keys (job_title, company_name, URL); accept
        # camelCase fallbacks in case the actor's output format changes.
        title = str(_first(item, "job_title", "jobTitle", "title")).strip()
        if not title:
            continue
        description = str(_first(item, "description", "jobDescription")).strip()
        posted = str(_first(item, "date", "postedDate")).strip()
        salary = str(_first(item, "salary")).strip()
        meta = " · ".join(part for part in [posted, salary] if part and part.upper() != "N/A")
        body = f"{description[:360]}…" if len(description) > 360 else (description or f"{title} opening.")
        summary = f"{meta}\n{body}" if meta else body
        postings.append(
            JobPosting(
                title=title,
                company=str(_first(item, "company_name", "companyName", "company") or "Unknown employer").strip() or "Unknown employer",
                location=str(_first(item, "location") or location or "Singapore").strip(),
                url=str(_first(item, "URL", "jobUrl", "url")).strip() or None,
                summary=summary,
                # Extract from the full title + description (not the truncated summary)
                # so skills mentioned deep in the posting are still captured.
                extracted_skills=_mock_extract(f"{title}. {description}"),
            )
        )
        if len(postings) >= max_jobs:
            break
    return (postings, None) if postings else (None, "no_results")


def _first(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _unique_titles() -> list[str]:
    with connect() as conn:
        return [row["skill_title"] for row in conn.execute("SELECT skill_title FROM unique_skills")]


def _generic_postings(target_role_id: str, role_title: str, location: str) -> list[JobPosting]:
    skills = [skill.canonical_title for skill in get_role_skills(target_role_id)[:6]]
    summary_skills = ", ".join(skills[:4]) or "stakeholder communication and role-specific delivery"
    return [
        JobPosting(
            title=role_title,
            company="Singapore employer sample",
            location=location,
            url=None,
            summary=f"Looking for a {role_title} with practical experience in {summary_skills}.",
            extracted_skills=[],
        ),
        JobPosting(
            title=f"Senior {role_title}",
            company="Regional team sample",
            location=location,
            url=None,
            summary=f"Role requires applied capability in {', '.join(skills[2:6]) or summary_skills}, plus communication and stakeholder management.",
            extracted_skills=[],
        ),
    ]


def _mock_extract(posting: str) -> list[str]:
    lowered = posting.lower()
    found = []
    for token in RAW_TO_CANDIDATE:
        if token in lowered:
            found.append(token)
    for title in _unique_titles():
        if title.lower() in lowered:
            found.append(title)
    return found


def _map_raw_skill(raw: str, unique_titles: list[str]) -> str | None:
    for title in unique_titles:
        if comparison_key(raw) == comparison_key(title):
            return title
    best = process.extractOne(raw, unique_titles, scorer=fuzz.token_sort_ratio)
    if best and best[1] >= 88:
        return best[0]
    candidate = RAW_TO_CANDIDATE.get(raw.lower())
    if candidate and candidate in unique_titles:
        return candidate
    return None
