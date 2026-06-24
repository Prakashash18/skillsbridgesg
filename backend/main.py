import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.routes import router
from app.data.db import ensure_db

load_dotenv()

app = FastAPI(title="SkillBridge SG API")

# Allowed CORS origins are configurable for deployment. Set ALLOWED_ORIGINS to a
# comma-separated list of frontend URLs (e.g. "https://skillbridge.vercel.app").
# Falls back to local dev origins when unset.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router, prefix="/api")
