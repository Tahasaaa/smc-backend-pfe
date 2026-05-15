from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine
from app.models import Base
from app.routers.backend_integration import router as backend_integration_router
from app.routers.demo_seed import router as demo_seed_router
from app.routers.explainability import router as explainability_router
from app.routers.rca import router as rca_router
from app.routers.training import router as training_router
from app.services.ml_service import load_model_artifacts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="V2 RCA API",
    description="Incident-level RCA assistant for telecom incidents",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    logger.info("Starting V2 RCA API...")

    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized.")

    info = load_model_artifacts()
    logger.info(
        "Model artifacts loaded successfully. classes=%s feature_count=%s trained_at=%s",
        info.get("classes"),
        info.get("feature_count"),
        info.get("trained_at_utc"),
    )


@app.get("/")
def root() -> dict:
    return {
        "message": "V2 RCA API is running",
        "status": "ok",
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "service": "v2_rca_api",
    }


app.include_router(rca_router)
app.include_router(training_router)
app.include_router(explainability_router)
app.include_router(backend_integration_router)
app.include_router(demo_seed_router)