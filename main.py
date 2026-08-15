import os

from app.api.routes import router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="workflow-copilot",
    description="Structured workflow planning, human approval, and audit API for operational requests.",
    version="0.2.0",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "WORKFLOW_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
