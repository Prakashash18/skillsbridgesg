# SkillBridge SG

SkillBridge SG is a data-grounded, AI-guided career-transition prototype for Singapore. It runs end-to-end in demo mode with no OpenAI key and no Apify token.

The user flow is chat-centric: the user describes their current profile or pastes LinkedIn/resume text, the assistant asks follow-up questions, maps the profile to SkillsFuture skills, suggests same-domain and cross-domain roles, shows gaps, explores job-demand signals, finds courses, and builds a 30-day plan.

## Run Backend

Use Python 3.11 or 3.12. Python 3.14 is not recommended for this prototype because some pinned backend native dependencies may not have compatible wheels.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

`POST /api/ingest` inspects and ingests the three SkillsFuture workbook filenames under `backend/app/data/`. These are backend reference files updated quarterly; users do not upload them. If the files are missing, the backend seeds a small demo dataset so the full flow still works.

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Environment

Create `backend/.env` from the example:

```bash
cd backend
cp .env.example .env
```

Then add your OpenAI key:

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
APIFY_TOKEN=
APIFY_ACTOR_ID=
DATABASE_URL=sqlite:///./storage/skillbridge.db
```

Missing keys are normal. Profile conversation, market validation, course search, and plan generation degrade to deterministic/mock fallbacks. With `OPENAI_API_KEY`, AI profile conversation and course search use the OpenAI-compatible client.

## Tests

```bash
cd backend
pytest
```
