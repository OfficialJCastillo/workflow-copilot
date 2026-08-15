from typing import Literal
from typing import Self

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


ApprovalStatus = Literal["draft", "pending_approval", "approved", "rejected"]


class WorkflowPlanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_text: str = Field(min_length=8, max_length=10_000)
    requester_role: str = Field(default="requester", min_length=2, max_length=120)
    team_name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def normalize_optional_team_name(self) -> Self:
        if self.team_name == "":
            self.team_name = None
        return self


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
    approval_status: ApprovalStatus
    decision_by: str | None = None
    decision_note: str | None = None
    decided_at: str | None = None


class WorkflowPlanListItem(BaseModel):
    workflow_id: str
    workflow_type: str
    summary: str
    urgency: str
    request_text: str
    step_status_counts: dict[str, int]
    completed_step_count: int
    total_step_count: int
    approval_status: ApprovalStatus
    created_at: str
    updated_at: str


class WorkflowStepStatusUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: str = Field(pattern="^(pending|in_progress|completed|blocked)$")
    actor: str = Field(default="workflow_api", min_length=2, max_length=120)


class ApprovalSubmissionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    actor: str = Field(min_length=2, max_length=120)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    actor: str = Field(min_length=2, max_length=120)
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_rejection_note(self) -> Self:
        if self.note == "":
            self.note = None
        if self.decision == "rejected" and not (self.note and self.note.strip()):
            raise ValueError("A rejection note is required.")
        return self


class WorkflowAuditEvent(BaseModel):
    event_id: str
    workflow_id: str
    event_type: str
    actor: str
    details: dict[str, str]
    created_at: str
