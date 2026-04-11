from pydantic import BaseModel
from pydantic import Field


class WorkflowPlanRequest(BaseModel):
    request_text: str = Field(min_length=8)
    requester_role: str = "requester"
    team_name: str | None = None


class WorkflowStep(BaseModel):
    step_id: str
    title: str
    owner: str
    status: str = "pending"
    rationale: str


class WorkflowPlanBase(BaseModel):
    workflow_type: str
    summary: str
    urgency: str
    steps: list[WorkflowStep]
    risks: list[str]
    missing_inputs: list[str]
    follow_up_questions: list[str]
    success_checks: list[str]


class WorkflowPlanResponse(WorkflowPlanBase):
    pass


class StoredWorkflowPlan(WorkflowPlanBase):
    workflow_id: str
    request_text: str
    requester_role: str
    team_name: str | None = None
    created_at: str
    updated_at: str


class WorkflowPlanListItem(BaseModel):
    workflow_id: str
    workflow_type: str
    summary: str
    urgency: str
    request_text: str
    created_at: str
    updated_at: str


class WorkflowStepStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|completed|blocked)$")
