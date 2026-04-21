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
        urgency = self._detect_urgency(request.request_text, workflow_type)
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
            summary=self._build_summary(template.summary, workflow_type, request.request_text, team_name),
            urgency=urgency,
            steps=steps,
            risks=self._expand_risks(template.risks, request.request_text, workflow_type),
            missing_inputs=self._expand_missing_inputs(template.missing_inputs, request.request_text, workflow_type),
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
        scores = {
            "incident_response": 0,
            "release_preparation": 0,
            "vendor_approval": 0,
            "onboarding": 0,
            "recurring_operations": 0,
        }
        weighted_phrases = {
            "incident_response": {
                "incident": 4,
                "outage": 5,
                "sev": 4,
                "rollback": 4,
                "degraded": 3,
                "mitigation": 2,
                "production issue": 4,
            },
            "release_preparation": {
                "release": 4,
                "launch": 4,
                "deploy": 3,
                "cutover": 4,
                "go live": 4,
                "hotfix": 3,
                "change freeze": 3,
            },
            "vendor_approval": {
                "vendor": 4,
                "procurement": 4,
                "purchase": 3,
                "contract": 4,
                "renewal": 3,
                "license": 3,
                "security review": 2,
            },
            "onboarding": {
                "onboard": 4,
                "new hire": 4,
                "training": 2,
                "orientation": 3,
                "week one": 2,
                "contractor": 2,
                "access": 2,
            },
            "recurring_operations": {
                "recurring": 4,
                "weekly": 3,
                "monthly": 3,
                "quarterly": 3,
                "cadence": 3,
                "runbook": 3,
                "checklist": 2,
                "rotation": 2,
                "report": 2,
            },
        }
        for workflow_type, phrases in weighted_phrases.items():
            for phrase, weight in phrases.items():
                if phrase in text:
                    scores[workflow_type] += weight

        ranked = sorted(
            scores.items(),
            key=lambda item: (item[1], self._workflow_rank(item[0])),
            reverse=True,
        )
        if ranked[0][1] == 0:
            return "recurring_operations"
        return ranked[0][0]

    def _detect_urgency(self, request_text: str, workflow_type: str) -> str:
        text = request_text.lower()
        high_tokens = ["today", "urgent", "asap", "immediately", "outage", "critical", "sev1", "p1", "blocked"]
        medium_tokens = [
            "this week",
            "next week",
            "soon",
            "thursday",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "end of week",
        ]
        if workflow_type == "incident_response":
            return "high"
        if any(token in text for token in high_tokens):
            return "high"
        if workflow_type == "release_preparation" and "customer" in text:
            return "high"
        if any(token in text for token in medium_tokens):
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

    def _build_summary(self, base_summary: str, workflow_type: str, request_text: str, team_name: str) -> str:
        text = request_text.lower()
        if workflow_type == "release_preparation" and "customer" in text:
            return "Plan a customer-facing release with approvals, validation, rollback readiness, and stakeholder coverage."
        if workflow_type == "vendor_approval" and any(token in text for token in ["data", "regulated", "security"]):
            return "Validate business need, procurement path, and data/security review before committing to a vendor."
        if workflow_type == "onboarding" and "remote" in text:
            return "Coordinate access, training, and remote setup so onboarding lands cleanly in the first week."
        if workflow_type == "recurring_operations" and any(token in text for token in ["weekly", "monthly", "quarterly", "cadence"]):
            return f"Turn {team_name}'s recurring request into a repeatable checklist with owners, cadence, and review points."
        return base_summary

    def _build_rationale(self, step_title: str, workflow_type: str) -> str:
        title = step_title.lower()
        if "assign" in title or "owner" in title:
            return f"This makes accountability explicit before the {workflow_type} workflow expands."
        if "confirm" in title or "document" in title:
            return "This locks down scope and reduces rework caused by assumptions."
        if "rollback" in title or "mitigation" in title:
            return "This protects the team if the primary execution path fails."
        if "schedule" in title or "set" in title:
            return "This creates predictable coordination points so the workflow does not drift."
        if "review" in title or "validation" in title:
            return "This reduces the chance of silent errors reaching stakeholders."
        return f"This step reduces ambiguity early in the {workflow_type} workflow."

    def _expand_risks(self, base_risks: list[str], request_text: str, workflow_type: str) -> list[str]:
        risks = list(base_risks)
        text = request_text.lower()
        if "customer" in text:
            risks.append("Customer impact raises the cost of unclear coordination.")
        if "api" in text or "access" in text:
            risks.append("System access or integration dependencies may delay execution.")
        if self._has_conflicting_timeline(text):
            risks.append("Urgency cues conflict with the stated timeline, so the team may optimize for the wrong date.")
        if self._is_vague_request(text):
            risks.append("The request is underspecified and may create avoidable rework.")
        if workflow_type == "vendor_approval" and any(token in text for token in ["data", "regulated", "security"]):
            risks.append("Vendor review may stall until data handling expectations are explicit.")
        if workflow_type == "onboarding" and any(token in text for token in ["remote", "contractor"]):
            risks.append("Distributed onboarding increases coordination risk around access and scheduling.")
        return self._dedupe(risks)

    def _expand_missing_inputs(self, base_missing_inputs: list[str], request_text: str, workflow_type: str) -> list[str]:
        missing_inputs = list(base_missing_inputs)
        text = request_text.lower()
        if self._is_vague_request(text):
            missing_inputs.append("Concrete deliverable or decision being requested.")
        if not any(
            token in text
            for token in [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "date",
                "week",
                "month",
                "quarter",
            ]
        ):
            missing_inputs.append("Target date or execution window.")
        if workflow_type == "release_preparation" and not any(token in text for token in ["rollback", "backout", "fallback"]):
            missing_inputs.append("Rollback trigger or fallback plan.")
        if workflow_type == "vendor_approval" and not any(token in text for token in ["budget", "spend", "cost"]):
            missing_inputs.append("Budget owner or expected spend range.")
        if workflow_type == "recurring_operations" and not any(
            token in text for token in ["daily", "weekly", "monthly", "quarterly", "cadence", "every"]
        ):
            missing_inputs.append("Recurring cadence or schedule.")
        if workflow_type == "onboarding" and "remote" in text and not any(
            token in text for token in ["timezone", "time zone", "location", "country"]
        ):
            missing_inputs.append("Work location or time zone.")
        return self._dedupe(missing_inputs)

    def _follow_up_questions(self, workflow_type: str, request_text: str) -> list[str]:
        text = request_text.lower()
        questions = ["Who owns final approval for this workflow?"]
        if self._has_conflicting_timeline(text):
            questions.append("The request sounds urgent and scheduled later. Which date should the team optimize for?")
        if self._is_vague_request(text):
            questions.append("What exact deliverable, decision, or outcome should count as done?")
        if workflow_type == "incident_response":
            questions.append("What service or customer segment is affected right now?")
        elif workflow_type == "release_preparation":
            questions.append("What is the rollback trigger if validation fails?")
            if not any(token in text for token in ["approver", "approval", "sign off", "signoff"]):
                questions.append("Who signs off on the release once validation passes?")
        elif workflow_type == "vendor_approval":
            questions.append("Will the vendor handle sensitive or customer data?")
            if not any(token in text for token in ["budget", "spend", "cost"]):
                questions.append("What budget owner or spend range should procurement use?")
        elif workflow_type == "onboarding":
            questions.append("What should the new teammate be able to complete by the end of week one?")
            if "remote" in text:
                questions.append("Which remote setup tasks must be finished before the first working session?")
        else:
            questions.append("What is the exact deadline or target milestone?")
        if "team" not in request_text.lower():
            questions.append("Which team is responsible for execution?")
        return self._dedupe(questions)

    def _timestamp(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    def _workflow_rank(self, workflow_type: str) -> int:
        order = {
            "incident_response": 5,
            "release_preparation": 4,
            "vendor_approval": 3,
            "onboarding": 2,
            "recurring_operations": 1,
        }
        return order[workflow_type]

    def _has_conflicting_timeline(self, text: str) -> bool:
        urgent = any(token in text for token in ["asap", "urgent", "immediately", "today"])
        distant = any(token in text for token in ["next month", "next quarter", "later", "eventually", "q1", "q2", "q3", "q4"])
        return urgent and distant

    def _is_vague_request(self, text: str) -> bool:
        words = [word.strip(".,!?") for word in text.split() if word.strip(".,!?")]
        return len(words) < 8 or ("need help" in text and len(words) < 12)

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered
