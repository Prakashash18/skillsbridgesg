# Deploying SkillBridge SG

Two services: a **FastAPI backend** (Render) and a **Next.js frontend** (Vercel).
The backend rebuilds its SkillsFuture catalogue (~2,027 roles) at build time, so
nothing large needs to be committed.

## 1. Backend → Render

1. Push this repo to GitHub.
2. Render dashboard → **New + → Blueprint** → select this repo. It reads
   [`render.yaml`](render.yaml) and creates the `skillbridge-api` web service.
3. Set the secret env vars (marked `sync: false`) in the Render UI:
   - `OPENAI_API_KEY` — your OpenAI key
   - `APIFY_TOKEN` — your Apify token (live Google Jobs)
   - `ALLOWED_ORIGINS` — leave blank for now; fill in after step 2 below
4. Deploy. The build runs `pip install` + `python -m scripts.ingest_datasets`
   (ingests the 3 Excel workbooks → SQLite). First boot serves the full catalogue.
5. Note the service URL, e.g. `https://skillbridge-api.onrender.com`.
   Verify: opening `<url>/health` returns `{"status":"ok"}`.

## 2. Frontend → Vercel

1. Vercel → **Add New → Project** → import this repo.
2. Set **Root Directory** to `frontend`.
3. Add env var `NEXT_PUBLIC_API_BASE_URL` = your Render URL from step 1.5.
4. Deploy. Note the Vercel URL, e.g. `https://skillbridge-sg.vercel.app`.

## 3. Connect them (CORS)

Back in Render, set `ALLOWED_ORIGINS` to your Vercel URL (comma-separated if more
than one), e.g. `https://skillbridge-sg.vercel.app`, then redeploy the backend.

## Notes

- **Free-tier sleep:** the Render free instance sleeps after ~15 min idle; the
  first request then takes ~30 s to wake. Ping `<url>/health` right before a demo.
- **Local dev** is unaffected — `ALLOWED_ORIGINS` falls back to `localhost:3000`
  and `NEXT_PUBLIC_API_BASE_URL` falls back to `http://localhost:8000`.
- **Secrets** stay out of git (`backend/.env` is gitignored); set them in the host UI.
