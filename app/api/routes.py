from app.schemas.models import WorkflowPlanRequest
from app.schemas.models import WorkflowPlanResponse
from app.services.copilot import WorkflowCopilot
from fastapi import APIRouter


router = APIRouter()
copilot = WorkflowCopilot()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/workflow/plan", response_model=WorkflowPlanResponse)
def plan_workflow(request: WorkflowPlanRequest) -> WorkflowPlanResponse:
    return copilot.build_plan(request)
