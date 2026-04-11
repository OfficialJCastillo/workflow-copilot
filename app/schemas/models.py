from pydantic import BaseModel
from pydantic import Field


class WorkflowPlanRequest(BaseModel):
    request_text: str = Field(min_length=8)
    requester_role: str = "requester"
    team_name: str | None = None


class WorkflowStep(BaseModel):
    title: str
    owner: str
    status: str = "pending"
    rationale: str


class WorkflowPlanResponse(BaseModel):
    workflow_type: str
    summary: str
    urgency: str
    steps: list[WorkflowStep]
    risks: list[str]
    missing_inputs: list[str]
    follow_up_questions: list[str]
    success_checks: list[str]
