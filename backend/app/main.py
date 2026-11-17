"""FastAPI entry point. Run: uv run uvicorn app.main:app --reload --port 8000"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api.routes import router
from app.api.runs import RunRegistry
from app.gateway.gateway import models_in_use
from app.stores import db
from app.stores.doc_index import DocIndex


def create_app(db_path: Path | None = None, audit_dir: Path | None = None, runs_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db_path = Path(db_path or config.DB_PATH)
        app.state.audit_dir = Path(audit_dir or config.AUDIT_DIR)
        app.state.runs = RunRegistry(runs_dir or config.DATA_DIR / "runs")   # finished briefings survive restarts
        app.state.index = None
        if app.state.db_path.exists():
            conn = db.connect(app.state.db_path, readonly=True)
            app.state.index = DocIndex.load(conn)          # loads the vector database (Qdrant) once
        yield

    app = FastAPI(title="Client Meeting Briefing API", version="0.2.0", lifespan=lifespan)
    # The Next.js dev server calls the API directly (so SSE streams are not buffered by a proxy).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],      # lets the page read the PDF's file name
    )

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "today": config.TODAY.isoformat(),
            "llm_mode": config.resolved_llm_mode(),
            "models": models_in_use(),          # display names, e.g. {"opus": "Opus 5.5", "haiku": "Haiku 5.5"}
            "db_ready": app.state.db_path.exists(),
            "index_ready": app.state.index is not None,
        }

    app.include_router(router)
    # The architecture diagrams (architecture/<prototype|production>/<name>.html), linked from the app.
    if config.ARCHITECTURE_DIR.exists():
        app.mount("/architecture", StaticFiles(directory=config.ARCHITECTURE_DIR, html=True), name="architecture")
    return app


app = create_app()
