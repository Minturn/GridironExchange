"""Gridiron Exchange API — :8200. All routes under /api; if the built frontend
(frontend/dist) is present it's served at / (HashRouter, so no SPA-fallback
gymnastics needed)."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import APP_VERSION, settings
from app.routes import admin, auth, market

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched = None
    if settings.enable_scheduler:
        from app.jobs import start_scheduler

        sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="Gridiron Exchange", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5190", "http://127.0.0.1:5190"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "version": APP_VERSION}


app.include_router(auth.router)
app.include_router(market.router)
app.include_router(admin.router)

_static = Path(__file__).resolve().parent.parent / settings.static_dir
if _static.is_dir():
    from fastapi.responses import FileResponse

    _index = _static / "index.html"

    @app.get("/", include_in_schema=False)
    def index():
        # never cache index.html → phones always pick up the latest JS/CSS bundle
        # (hashed assets under /assets are safe to cache; the fresh index points at them)
        return FileResponse(_index, headers={"Cache-Control": "no-store, must-revalidate"})

    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
