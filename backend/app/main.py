"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.experiment_detail import router as experiment_detail_router
from app.api.experiment_report import router as experiment_report_router
from app.api.experiment_tree import router as experiment_tree_router
from app.api.git import router as git_router
from app.api.papers import router as papers_router
from app.api.project_wizard import router as project_wizard_router
from app.core.config import settings

app = FastAPI(
    title="Research Companion API",
    description="科研分身框架 API",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(experiment_detail_router)
app.include_router(experiment_report_router)
app.include_router(experiment_tree_router)
app.include_router(papers_router)
app.include_router(git_router)
app.include_router(project_wizard_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
