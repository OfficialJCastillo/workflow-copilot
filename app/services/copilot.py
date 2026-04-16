from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
import uuid

from app.schemas.models import StoredWorkflowPlan
from app.schemas.models import WorkflowPlanRequest
from app.schemas.models import WorkflowPlanResponse
from app.schemas.models import WorkflowStep
from app.services.store import WorkflowStore


@dataclass(frozen=True)
class WorkflowTemplate:
    workflow_type: str
    summary: str
    steps: list[tuple[str, str]]
    risks: list[str]
    missing_inputs: list[str]
    success_checks: list[str]


class WorkflowCopilot:
    def __init__(self, store: WorkflowStore | None = None) -> None:
        self.store = store

    def build_plan(self, request: WorkflowPlanRequest) -> WorkflowPlanResponse:
        workflow_type = self._detect_workflow_type(request.request_text)
        template = self._template_for(workflow_type)
        urgency = self._detect_urgency(request.request_text)
        owner = request.requester_role
        team_name = request.team_name or "the team"

        steps = [
            WorkflowStep(
                step_id=f"step-{index}",
                title=title.format(team_name=team_name),
                owner=assigned_owner if assigned_owner != "requester" else owner,
                rationale=self._build_rationale(title, workflow_type),
            )
            for index, (title, assigned_owner) in enumerate(template.steps, start=1)
        ]

        return WorkflowPlanResponse(
            workflow_type=template.workflow_type,
            summary=template.summary,
            urgency=urgency,
            steps=steps,
            risks=self._expand_risks(template.risks, request.request_text),
            missing_inputs=self._expand_missing_inputs(template.missing_inputs, request.request_text),
            follow_up_questions=self._follow_up_questions(workflow_type, request.request_text),
            success_checks=template.success_checks,
        )

    def create_plan(self, request: WorkflowPlanRequest) -> StoredWorkflowPlan:
        plan = self.build_plan(request)
        timestamp = self._timestamp()
        return self._store().save_plan(
            workflow_id=f"wf-{uuid.uuid4().hex[:12]}",
            request_text=request.request_text,
            requester_role=request.requester_role,
            team_name=request.team_name,
            workflow_type=plan.workflow_type,
            summary=plan.summary,
            urgency=plan.urgency,
            steps=plan.steps,
            risks=plan.risks,
            missing_inputs=plan.missing_inputs,
            follow_up_questions=plan.follow_up_questions,
            success_checks=plan.success_checks,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def list_plans(self) -> list[StoredWorkflowPlan]:
        store = self._store()
        summaries = store.list_plans()
        plans = [store.get_plan(item.workflow_id) for item in summaries]
        return [plan for plan in plans if plan is not None]

    def get_plan(self, workflow_id: str) -> StoredWorkflowPlan | None:
        return self._store().get_plan(workflow_id)

    def update_step_status(self, workflow_id: str, step_id: str, status: str) -> StoredWorkflowPlan | None:
        return self._store().update_step_status(
            workflow_id=workflow_id,
            step_id=step_id,
            status=status,
            updated_at=self._timestamp(),
        )

    def _store(self) -> WorkflowStore:
        if self.store is None:
            self.store = WorkflowStore()
        return self.store

    def _detect_workflow_type(self, request_text: str) -> str:
        text = request_text.lower()
        if any(token in text for token in ["incident", "outage", "sev", "rollback"]):
            return "incident_response"
        if any(token in text for token in ["release", "launch", "deploy", "cutover"]):
            return "release_preparation"
        if any(token in text for token in ["vendor", "procurement", "purchase", "tooling"]):
            return "vendor_approval"
        if any(token in text for token in ["onboard", "new hire", "access", "training"]):
            return "onboarding"
        return "recurring_operations"

    def _detect_urgency(self, request_text: str) -> str:
        text = request_text.lower()
        if any(token in text for token in ["today", "urgent", "asap", "immediately", "outage"]):
            return "high"
        if any(token in text for token in ["this week", "next week", "soon", "thursday", "friday"]):
            return "medium"
        return "normal"

    def _template_for(self, workflow_type: str) -> WorkflowTemplate:
        templates = {
            "incident_response": WorkflowTemplate(
                workflow_type="incident_response",
                summary="Stabilize the issue, assign ownership, and manage communication before deeper follow-up work.",
                steps=[
                    ("Assign an incident lead for {team_name}", "requester"),
                    ("Confirm customer impact and current severity", "requester"),
                    ("Define the immediate mitigation or rollback path", "incident lead"),
                    ("Set communication checkpoints for stakeholders", "incident lead"),
                    ("Capture follow-up work after service is stable", "incident lead"),
                ],
                risks=[
                    "Unclear ownership slows mitigation decisions.",
                    "Communication gaps create avoidable escalation churn.",
                ],
                missing_inputs=[
                    "Current severity level and customer impact.",
                    "Named incident lead or backup owner.",
                ],
                success_checks=[
                    "An owner is assigned.",
                    "Mitigation path is defined.",
                    "Stakeholder update cadence is clear.",
                ],
            ),
            "release_preparation": WorkflowTemplate(
                workflow_type="release_preparation",
                summary="Plan a controlled release with approvals, validation, and rollback readiness.",
                steps=[
                    ("Confirm release scope and target date for {team_name}", "requester"),
                    ("Freeze the change list and confirm approvers", "requester"),
                    ("Run pre-release validation and document rollback steps", "release manager"),
                    ("Prepare release communications and support coverage", "release manager"),
                    ("Schedule post-release verification checks", "release manager"),
                ],
                risks=[
                    "Customer-facing changes increase rollback sensitivity.",
                    "Late scope changes weaken release confidence.",
                ],
                missing_inputs=[
                    "Exact release date and deployment window.",
                    "Rollback owner and verification checklist.",
                ],
                success_checks=[
                    "Scope is frozen.",
                    "Rollback steps are documented.",
                    "Verification owners are assigned.",
                ],
            ),
            "vendor_approval": WorkflowTemplate(
                workflow_type="vendor_approval",
                summary="Validate business need, approvals, security review, and purchasing path before commitment.",
                steps=[
                    ("Document the business need and expected outcome", "requester"),
                    ("Confirm budget owner and approval path", "requester"),
                    ("Run security and data handling review", "security"),
                    ("Review contract and procurement requirements", "procurement"),
                    ("Decide go or no-go with decision notes", "requester"),
                ],
                risks=[
                    "Security review can block timeline assumptions.",
                    "Budget approval may lag if ownership is unclear.",
                ],
                missing_inputs=[
                    "Estimated spend and contract term.",
                    "Whether customer or regulated data is involved.",
                ],
                success_checks=[
                    "Approval path is known.",
                    "Security review is complete.",
                    "Decision and owner are documented.",
                ],
            ),
            "onboarding": WorkflowTemplate(
                workflow_type="onboarding",
                summary="Coordinate access, training, and early deliverables for a clean onboarding flow.",
                steps=[
                    ("Confirm start date, role scope, and manager", "requester"),
                    ("Prepare account access and baseline tooling", "it"),
                    ("Schedule onboarding sessions and documentation review", "manager"),
                    ("Assign a first-week checklist and buddy", "manager"),
                    ("Review completion status at the end of week one", "manager"),
                ],
                risks=[
                    "Missing access delays ramp-up immediately.",
                    "Undefined first-week goals create weak onboarding momentum.",
                ],
                missing_inputs=[
                    "Start date and manager name.",
                    "Required systems and training modules.",
                ],
                success_checks=[
                    "Access is ready by day one.",
                    "First-week goals are assigned.",
                    "Manager review is scheduled.",
                ],
            ),
            "recurring_operations": WorkflowTemplate(
                workflow_type="recurring_operations",
                summary="Turn a loose operational request into a repeatable checklist with owners and checkpoints.",
                steps=[
                    ("Define the requested outcome and operating cadence", "requester"),
                    ("List dependencies, approvers, and handoffs", "requester"),
                    ("Create the execution checklist", "operations"),
                    ("Add a review checkpoint for exceptions", "operations"),
                    ("Record completion and next scheduled run", "operations"),
                ],
                risks=[
                    "Hidden dependencies cause last-minute blockers.",
                    "No clear review point makes recurring work drift over time.",
                ],
                missing_inputs=[
                    "Cadence, owner, and deadline.",
                    "Dependencies or systems involved.",
                ],
                success_checks=[
                    "Checklist is defined.",
                    "Owner is assigned.",
                    "Next run is scheduled.",
                ],
            ),
        }
        return templates[workflow_type]

    def _build_rationale(self, step_title: str, workflow_type: str) -> str:
        return f"This step reduces ambiguity early in the {workflow_type} workflow."

    def _expand_risks(self, base_risks: list[str], request_text: str) -> list[str]:
        risks = list(base_risks)
        text = request_text.lower()
        if "customer" in text:
            risks.append("Customer impact raises the cost of unclear coordination.")
        if "api" in text or "access" in text:
            risks.append("System access or integration dependencies may delay execution.")
        return risks

    def _expand_missing_inputs(self, base_missing_inputs: list[str], request_text: str) -> list[str]:
        missing_inputs = list(base_missing_inputs)
        text = request_text.lower()
        if not any(token in text for token in ["monday", "tuesday", "wednesday", "thursday", "friday", "date"]):
            missing_inputs.append("Target date or execution window.")
        return missing_inputs

    def _follow_up_questions(self, workflow_type: str, request_text: str) -> list[str]:
        questions = ["Who owns final approval for this workflow?"]
        if workflow_type == "incident_response":
            questions.append("What service or customer segment is affected right now?")
        elif workflow_type == "release_preparation":
            questions.append("What is the rollback trigger if validation fails?")
        elif workflow_type == "vendor_approval":
            questions.append("Will the vendor handle sensitive or customer data?")
        else:
            questions.append("What is the exact deadline or target milestone?")
        if "team" not in request_text.lower():
            questions.append("Which team is responsible for execution?")
        return questions

    def _timestamp(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
