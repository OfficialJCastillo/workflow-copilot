from fastapi import APIRouter
from fastapi import HTTPException
from app.api.demo_ui import render_demo_ui
from app.schemas.models import ApprovalDecisionRequest
from app.schemas.models import ApprovalSubmissionRequest
from app.schemas.models import WorkflowPlanRequest
from app.schemas.models import WorkflowAuditEvent
from app.schemas.models import WorkflowPlanListItem
from app.schemas.models import WorkflowPlanResponse
from app.schemas.models import WorkflowStepStatusUpdate
from app.schemas.models import StoredWorkflowPlan
from app.services.copilot import WorkflowCopilot
from app.services.store import InvalidApprovalTransition
from sqlalchemy.exc import SQLAlchemyError


router = APIRouter()
copilot = WorkflowCopilot()


@router.get("/", include_in_schema=False)
def demo_ui():
    return render_demo_ui()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def readiness() -> dict[str, str]:
    try:
        database_backend = copilot.database_readiness()
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from error
    return {"status": "ready", "database": database_backend}


@router.post("/workflow/plan", response_model=WorkflowPlanResponse)
def plan_workflow(request: WorkflowPlanRequest) -> WorkflowPlanResponse:
    return copilot.build_plan(request)


@router.post("/workflow/plans", response_model=StoredWorkflowPlan)
def create_workflow_plan(request: WorkflowPlanRequest) -> StoredWorkflowPlan:
    return copilot.create_plan(request)


@router.get("/workflow/plans", response_model=list[WorkflowPlanListItem])
def list_workflow_plans() -> list[WorkflowPlanListItem]:
    return copilot.list_plans()


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
    plan = copilot.update_step_status(workflow_id, step_id, request.status, request.actor)
    if plan is None:
        raise HTTPException(status_code=404, detail="Workflow plan or step not found.")
    return plan


@router.post("/workflow/plans/{workflow_id}/approval-requests", response_model=StoredWorkflowPlan)
def submit_workflow_plan_for_approval(
    workflow_id: str,
    request: ApprovalSubmissionRequest,
) -> StoredWorkflowPlan:
    try:
        plan = copilot.submit_for_approval(workflow_id, request.actor)
    except InvalidApprovalTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if plan is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return plan


@router.post("/workflow/plans/{workflow_id}/approval-decisions", response_model=StoredWorkflowPlan)
def decide_workflow_plan(
    workflow_id: str,
    request: ApprovalDecisionRequest,
) -> StoredWorkflowPlan:
    try:
        plan = copilot.decide_plan(
            workflow_id=workflow_id,
            decision=request.decision,
            actor=request.actor,
            note=request.note,
        )
    except InvalidApprovalTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if plan is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return plan


@router.get("/workflow/plans/{workflow_id}/audit-events", response_model=list[WorkflowAuditEvent])
def list_workflow_audit_events(workflow_id: str) -> list[WorkflowAuditEvent]:
    events = copilot.list_audit_events(workflow_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return events
