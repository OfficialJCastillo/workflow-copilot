from fastapi import APIRouter
from fastapi import HTTPException
from app.schemas.models import WorkflowPlanRequest
from app.schemas.models import WorkflowPlanListItem
from app.schemas.models import WorkflowPlanResponse
from app.schemas.models import WorkflowStepStatusUpdate
from app.schemas.models import StoredWorkflowPlan
from app.services.copilot import WorkflowCopilot


router = APIRouter()
copilot = WorkflowCopilot()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/workflow/plan", response_model=WorkflowPlanResponse)
def plan_workflow(request: WorkflowPlanRequest) -> WorkflowPlanResponse:
    return copilot.build_plan(request)


@router.post("/workflow/plans", response_model=StoredWorkflowPlan)
def create_workflow_plan(request: WorkflowPlanRequest) -> StoredWorkflowPlan:
    return copilot.create_plan(request)


@router.get("/workflow/plans", response_model=list[WorkflowPlanListItem])
def list_workflow_plans() -> list[WorkflowPlanListItem]:
    plans = copilot.list_plans()
    return [
        WorkflowPlanListItem(
            workflow_id=plan.workflow_id,
            workflow_type=plan.workflow_type,
            summary=plan.summary,
            urgency=plan.urgency,
            request_text=plan.request_text,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
        for plan in plans
    ]


@router.get("/workflow/plans/{workflow_id}", response_model=StoredWorkflowPlan)
def get_workflow_plan(workflow_id: str) -> StoredWorkflowPlan:
    plan = copilot.get_plan(workflow_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return plan


@router.patch("/workflow/plans/{workflow_id}/steps/{step_id}", response_model=StoredWorkflowPlan)
def update_workflow_step_status(
    workflow_id: str,
    step_id: str,
    request: WorkflowStepStatusUpdate,
) -> StoredWorkflowPlan:
    plan = copilot.update_step_status(workflow_id, step_id, request.status)
    if plan is None:
        raise HTTPException(status_code=404, detail="Workflow plan or step not found.")
    return plan
