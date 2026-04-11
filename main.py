from app.api.routes import router
from fastapi import FastAPI


app = FastAPI(
    title="workflow-copilot",
    description="Structured workflow planning API for operational requests.",
    version="0.1.0",
)
app.include_router(router)
