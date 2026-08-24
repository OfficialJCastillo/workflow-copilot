import os
from typing import Annotated

from fastapi import APIRouter
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from app.api.demo_ui import render_demo_ui
from app.schemas.models import ApprovalDecisionRequest
from app.schemas.models import ApprovalSubmissionRequest
from app.schemas.models import EvidenceDeletionRequest
from app.schemas.models import EvidenceSearchRequest
from app.schemas.models import EvidenceSearchResponse
from app.schemas.models import GroundedAnswerRequest
from app.schemas.models import GroundedAnswerResponse
from app.schemas.models import HybridIndexStatusResponse
from app.schemas.models import WorkflowPlanRequest
from app.schemas.models import WorkflowAuditEvent
from app.schemas.models import WorkflowPlanListItem
from app.schemas.models import WorkflowPlanResponse
from app.schemas.models import WorkflowStepStatusUpdate
from app.schemas.models import WorkflowEvidence
from app.schemas.models import StoredWorkflowPlan
from app.schemas.models import ServiceMetricsResponse
from app.services.copilot import WorkflowCopilot
from app.services.observability import metrics_collector
from app.services.evidence import EvidenceExtractionError
from app.services.evidence import EvidenceTooLarge
from app.services.evidence import MAX_EVIDENCE_BYTES
from app.services.evidence import UnsupportedEvidenceType
from app.services.store import InvalidApprovalTransition
from sqlalchemy.exc import SQLAlchemyError


router = APIRouter()
hybrid_index_path = os.getenv(
    "WORKFLOW_HYBRID_INDEX_PATH",
    "data/workflow_hybrid_index.db",
).strip()
compact_hybrid_index_on_delete = os.getenv(
    "WORKFLOW_HYBRID_INDEX_COMPACT_ON_DELETE",
    "0",
).strip().lower() in {"1", "true", "yes", "on"}
copilot = WorkflowCopilot(
    hybrid_index_path=hybrid_index_path or None,
    compact_hybrid_index_on_delete=compact_hybrid_index_on_delete,
)


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


@router.get("/metrics", response_model=ServiceMetricsResponse)
def service_metrics() -> ServiceMetricsResponse:
    return metrics_collector.snapshot()


@router.get("/metrics/retrieval-index", response_model=HybridIndexStatusResponse)
def retrieval_index_metrics() -> HybridIndexStatusResponse:
    return copilot.hybrid_index_status()


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


@router.post(
    "/workflow/plans/{workflow_id}/evidence",
    response_model=WorkflowEvidence,
    status_code=201,
)
async def attach_workflow_evidence(
    workflow_id: str,
    file: Annotated[UploadFile, File(description="UTF-8 text or PDF evidence")],
    actor: Annotated[str, Form(min_length=2, max_length=120)] = "workflow_api",
) -> WorkflowEvidence:
    content = await file.read(MAX_EVIDENCE_BYTES + 1)
    await file.close()
    normalized_actor = actor.strip()
    if len(normalized_actor) < 2:
        raise HTTPException(status_code=422, detail="Evidence actor must contain at least two characters.")
    try:
        evidence = copilot.attach_evidence(
            workflow_id=workflow_id,
            filename=file.filename or "upload",
            media_type=file.content_type or "application/octet-stream",
            content=content,
            actor=normalized_actor,
        )
    except UnsupportedEvidenceType as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except EvidenceTooLarge as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except EvidenceExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if evidence is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return evidence


@router.get(
    "/workflow/plans/{workflow_id}/evidence",
    response_model=list[WorkflowEvidence],
)
def list_workflow_evidence(workflow_id: str) -> list[WorkflowEvidence]:
    evidence = copilot.list_evidence(workflow_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return evidence


@router.delete(
    "/workflow/plans/{workflow_id}/evidence/{evidence_id}",
    response_model=WorkflowEvidence,
)
def delete_workflow_evidence(
    workflow_id: str,
    evidence_id: str,
    request: EvidenceDeletionRequest,
) -> WorkflowEvidence:
    evidence = copilot.delete_evidence(
        workflow_id=workflow_id,
        evidence_id=evidence_id,
        actor=request.actor,
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="Workflow evidence not found.")
    return evidence


@router.post(
    "/workflow/plans/{workflow_id}/evidence/search",
    response_model=EvidenceSearchResponse,
)
def search_workflow_evidence(
    workflow_id: str,
    request: EvidenceSearchRequest,
) -> EvidenceSearchResponse:
    results = copilot.search_evidence(
        workflow_id=workflow_id,
        query=request.query,
        top_k=request.top_k,
        strategy=request.strategy,
    )
    if results is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return results


@router.post(
    "/workflow/plans/{workflow_id}/evidence/answer",
    response_model=GroundedAnswerResponse,
)
def answer_workflow_question_from_evidence(
    workflow_id: str,
    request: GroundedAnswerRequest,
) -> GroundedAnswerResponse:
    answer = copilot.answer_from_evidence(
        workflow_id=workflow_id,
        query=request.query,
        top_k=request.top_k,
        max_claims=request.max_claims,
        strategy=request.strategy,
    )
    if answer is None:
        raise HTTPException(status_code=404, detail="Workflow plan not found.")
    return answer
