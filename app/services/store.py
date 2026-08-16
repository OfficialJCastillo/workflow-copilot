from dataclasses import dataclass
import os
import uuid

from sqlalchemy import Engine
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy import update

from app.schemas.models import StoredWorkflowPlan
from app.schemas.models import WorkflowAuditEvent
from app.schemas.models import WorkflowEvidence
from app.schemas.models import WorkflowPlanListItem
from app.schemas.models import WorkflowStep
from app.services.database import create_database_engine
from app.services.database import database_url_from_path
from app.services.database import metadata
from app.services.database import workflow_audit_events
from app.services.database import workflow_evidence
from app.services.database import workflow_plans
from app.services.retrieval import SearchDocument


STEP_STATUSES = ("pending", "in_progress", "completed", "blocked")


class InvalidApprovalTransition(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceSaveResult:
    evidence: WorkflowEvidence
    created: bool


class WorkflowStore:
    def __init__(
        self,
        database_path: str | None = None,
        database_url: str | None = None,
        engine: Engine | None = None,
        initialize_schema: bool | None = None,
    ) -> None:
        if database_path is not None and database_url is not None:
            raise ValueError("Provide either database_path or database_url, not both.")

        resolved_url = database_url
        if database_path is not None:
            resolved_url = database_url_from_path(database_path)
        self.engine = engine or create_database_engine(resolved_url)

        if initialize_schema is None:
            initialize_schema = os.getenv("WORKFLOW_AUTO_CREATE_SCHEMA", "1") == "1"
        if initialize_schema:
            metadata.create_all(self.engine)

    @property
    def database_backend(self) -> str:
        return self.engine.dialect.name

    def check_connection(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(select(1)).scalar_one()

    def save_plan(
        self,
        workflow_id: str,
        request_text: str,
        requester_role: str,
        team_name: str | None,
        workflow_type: str,
        summary: str,
        urgency: str,
        steps: list[WorkflowStep],
        risks: list[str],
        missing_inputs: list[str],
        follow_up_questions: list[str],
        success_checks: list[str],
        created_at: str,
        updated_at: str,
    ) -> StoredWorkflowPlan:
        payload = {
            "workflow_id": workflow_id,
            "request_text": request_text,
            "requester_role": requester_role,
            "team_name": team_name,
            "workflow_type": workflow_type,
            "summary": summary,
            "urgency": urgency,
            "steps_json": [step.model_dump() for step in steps],
            "risks_json": risks,
            "missing_inputs_json": missing_inputs,
            "follow_up_questions_json": follow_up_questions,
            "success_checks_json": success_checks,
            "created_at": created_at,
            "updated_at": updated_at,
            "approval_status": "draft",
            "decision_by": None,
            "decision_note": None,
            "decided_at": None,
        }
        with self.engine.begin() as connection:
            connection.execute(insert(workflow_plans).values(**payload))
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type="plan_created",
                actor=requester_role,
                details={"approval_status": "draft"},
                created_at=created_at,
            )
        return self._stored_plan(payload)

    def list_plans(self) -> list[WorkflowPlanListItem]:
        statement = select(
            workflow_plans.c.workflow_id,
            workflow_plans.c.workflow_type,
            workflow_plans.c.summary,
            workflow_plans.c.urgency,
            workflow_plans.c.request_text,
            workflow_plans.c.steps_json,
            workflow_plans.c.approval_status,
            workflow_plans.c.created_at,
            workflow_plans.c.updated_at,
        ).order_by(
            workflow_plans.c.updated_at.desc(),
            workflow_plans.c.created_at.desc(),
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()

        list_items = []
        for row in rows:
            steps = [WorkflowStep(**step) for step in row["steps_json"]]
            step_status_counts = self._step_status_counts(steps)
            list_items.append(
                WorkflowPlanListItem(
                    workflow_id=row["workflow_id"],
                    workflow_type=row["workflow_type"],
                    summary=row["summary"],
                    urgency=row["urgency"],
                    request_text=row["request_text"],
                    step_status_counts=step_status_counts,
                    completed_step_count=step_status_counts["completed"],
                    total_step_count=len(steps),
                    approval_status=row["approval_status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return list_items

    def get_plan(self, workflow_id: str) -> StoredWorkflowPlan | None:
        statement = select(workflow_plans).where(workflow_plans.c.workflow_id == workflow_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return self._stored_plan(row) if row is not None else None

    def update_step_status(
        self,
        workflow_id: str,
        step_id: str,
        status: str,
        actor: str,
        updated_at: str,
    ) -> StoredWorkflowPlan | None:
        plan = self.get_plan(workflow_id)
        if plan is None:
            return None
        updated_steps = []
        step_found = False
        for step in plan.steps:
            if step.step_id == step_id:
                updated_steps.append(step.model_copy(update={"status": status}))
                step_found = True
            else:
                updated_steps.append(step)
        if not step_found:
            return None

        with self.engine.begin() as connection:
            connection.execute(
                update(workflow_plans)
                .where(workflow_plans.c.workflow_id == workflow_id)
                .values(
                    steps_json=[step.model_dump() for step in updated_steps],
                    updated_at=updated_at,
                )
            )
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type="step_status_updated",
                actor=actor,
                details={"step_id": step_id, "status": status},
                created_at=updated_at,
            )
        return plan.model_copy(update={"steps": updated_steps, "updated_at": updated_at})

    def submit_for_approval(self, workflow_id: str, actor: str, submitted_at: str) -> StoredWorkflowPlan | None:
        plan = self.get_plan(workflow_id)
        if plan is None:
            return None
        if plan.approval_status not in {"draft", "rejected"}:
            raise InvalidApprovalTransition(
                f"Cannot submit a plan with approval status '{plan.approval_status}'."
            )

        with self.engine.begin() as connection:
            result = connection.execute(
                update(workflow_plans)
                .where(
                    workflow_plans.c.workflow_id == workflow_id,
                    workflow_plans.c.approval_status == plan.approval_status,
                )
                .values(
                    approval_status="pending_approval",
                    decision_by=None,
                    decision_note=None,
                    decided_at=None,
                    updated_at=submitted_at,
                )
            )
            if result.rowcount != 1:
                raise InvalidApprovalTransition(
                    "Approval status changed while the plan was being submitted."
                )
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type="approval_requested",
                actor=actor,
                details={
                    "previous_status": plan.approval_status,
                    "approval_status": "pending_approval",
                },
                created_at=submitted_at,
            )

        return self.get_plan(workflow_id)

    def decide_plan(
        self,
        workflow_id: str,
        decision: str,
        actor: str,
        note: str | None,
        decided_at: str,
    ) -> StoredWorkflowPlan | None:
        if decision not in {"approved", "rejected"}:
            raise InvalidApprovalTransition(f"Unsupported approval decision '{decision}'.")

        plan = self.get_plan(workflow_id)
        if plan is None:
            return None
        if plan.approval_status != "pending_approval":
            raise InvalidApprovalTransition(
                f"Cannot decide a plan with approval status '{plan.approval_status}'."
            )

        with self.engine.begin() as connection:
            result = connection.execute(
                update(workflow_plans)
                .where(
                    workflow_plans.c.workflow_id == workflow_id,
                    workflow_plans.c.approval_status == "pending_approval",
                )
                .values(
                    approval_status=decision,
                    decision_by=actor,
                    decision_note=note,
                    decided_at=decided_at,
                    updated_at=decided_at,
                )
            )
            if result.rowcount != 1:
                raise InvalidApprovalTransition(
                    "Approval status changed while the decision was being recorded."
                )
            details = {"approval_status": decision}
            if note:
                details["note"] = note
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type=f"plan_{decision}",
                actor=actor,
                details=details,
                created_at=decided_at,
            )

        return self.get_plan(workflow_id)

    def list_audit_events(self, workflow_id: str) -> list[WorkflowAuditEvent] | None:
        if self.get_plan(workflow_id) is None:
            return None
        statement = (
            select(workflow_audit_events)
            .where(workflow_audit_events.c.workflow_id == workflow_id)
            .order_by(
                workflow_audit_events.c.created_at.asc(),
                workflow_audit_events.c.event_id.asc(),
            )
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            WorkflowAuditEvent(
                event_id=row["event_id"],
                workflow_id=row["workflow_id"],
                event_type=row["event_type"],
                actor=row["actor"],
                details=row["details_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_evidence(
        self,
        *,
        workflow_id: str,
        filename: str,
        media_type: str,
        content_text: str,
        excerpt: str,
        source_sha256: str,
        page_count: int | None,
        character_count: int,
        actor: str,
        created_at: str,
    ) -> EvidenceSaveResult | None:
        evidence_id = f"evi-{uuid.uuid4().hex[:12]}"
        payload = {
            "evidence_id": evidence_id,
            "workflow_id": workflow_id,
            "filename": filename,
            "media_type": media_type,
            "content_text": content_text,
            "excerpt": excerpt,
            "source_sha256": source_sha256,
            "page_count": page_count,
            "character_count": character_count,
            "created_at": created_at,
        }
        with self.engine.begin() as connection:
            plan_exists = connection.execute(
                select(workflow_plans.c.workflow_id).where(
                    workflow_plans.c.workflow_id == workflow_id
                )
            ).first()
            if plan_exists is None:
                return None

            existing = connection.execute(
                select(workflow_evidence).where(
                    workflow_evidence.c.workflow_id == workflow_id,
                    workflow_evidence.c.source_sha256 == source_sha256,
                )
            ).mappings().first()
            if existing is not None:
                return EvidenceSaveResult(
                    evidence=self._workflow_evidence(existing),
                    created=False,
                )

            connection.execute(insert(workflow_evidence).values(**payload))
            connection.execute(
                update(workflow_plans)
                .where(workflow_plans.c.workflow_id == workflow_id)
                .values(updated_at=created_at)
            )
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type="evidence_attached",
                actor=actor,
                details={
                    "evidence_id": evidence_id,
                    "filename": filename,
                    "media_type": media_type,
                },
                created_at=created_at,
            )
        return EvidenceSaveResult(
            evidence=self._workflow_evidence(payload),
            created=True,
        )

    def record_evidence_index_refresh(
        self,
        *,
        workflow_id: str,
        actor: str,
        fingerprint: str,
        chunk_count: int,
        cache_status: str,
        removed_corpus_count: int,
        index_size_bytes: int,
        created_at: str,
        compacted: bool = False,
        compaction_reclaimed_bytes: int = 0,
        removed_namespace_count: int = 0,
    ) -> None:
        with self.engine.begin() as connection:
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type="evidence_index_refreshed",
                actor=actor,
                details={
                    "fingerprint": fingerprint[:12],
                    "chunk_count": str(chunk_count),
                    "cache_status": cache_status,
                    "removed_corpus_count": str(removed_corpus_count),
                    "index_size_bytes": str(index_size_bytes),
                    "compacted": str(compacted).lower(),
                    "compaction_reclaimed_bytes": str(compaction_reclaimed_bytes),
                    "removed_namespace_count": str(removed_namespace_count),
                },
                created_at=created_at,
            )

    def delete_evidence(
        self,
        *,
        workflow_id: str,
        evidence_id: str,
        actor: str,
        deleted_at: str,
    ) -> WorkflowEvidence | None:
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(workflow_evidence).where(
                    workflow_evidence.c.workflow_id == workflow_id,
                    workflow_evidence.c.evidence_id == evidence_id,
                )
            ).mappings().first()
            if existing is None:
                return None

            connection.execute(
                delete(workflow_evidence).where(
                    workflow_evidence.c.workflow_id == workflow_id,
                    workflow_evidence.c.evidence_id == evidence_id,
                )
            )
            connection.execute(
                update(workflow_plans)
                .where(workflow_plans.c.workflow_id == workflow_id)
                .values(updated_at=deleted_at)
            )
            self._record_audit_event(
                connection=connection,
                workflow_id=workflow_id,
                event_type="evidence_deleted",
                actor=actor,
                details={
                    "evidence_id": evidence_id,
                    "filename": existing["filename"],
                },
                created_at=deleted_at,
            )
        return self._workflow_evidence(existing)

    def list_evidence(self, workflow_id: str) -> list[WorkflowEvidence] | None:
        if self.get_plan(workflow_id) is None:
            return None
        statement = (
            select(workflow_evidence)
            .where(workflow_evidence.c.workflow_id == workflow_id)
            .order_by(
                workflow_evidence.c.created_at.asc(),
                workflow_evidence.c.evidence_id.asc(),
            )
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._workflow_evidence(row) for row in rows]

    def list_search_documents(self, workflow_id: str) -> list[SearchDocument] | None:
        if self.get_plan(workflow_id) is None:
            return None
        statement = (
            select(
                workflow_evidence.c.evidence_id,
                workflow_evidence.c.filename,
                workflow_evidence.c.content_text,
            )
            .where(workflow_evidence.c.workflow_id == workflow_id)
            .order_by(
                workflow_evidence.c.created_at.asc(),
                workflow_evidence.c.evidence_id.asc(),
            )
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            SearchDocument(
                source_id=row["evidence_id"],
                citation_id=self._citation_id(row["evidence_id"]),
                filename=row["filename"],
                content=row["content_text"],
            )
            for row in rows
        ]

    def count_plans(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(workflow_plans)).scalar_one()

    def _record_audit_event(
        self,
        connection,
        workflow_id: str,
        event_type: str,
        actor: str,
        details: dict[str, str],
        created_at: str,
    ) -> None:
        connection.execute(
            insert(workflow_audit_events).values(
                event_id=f"evt-{uuid.uuid4().hex[:12]}",
                workflow_id=workflow_id,
                event_type=event_type,
                actor=actor,
                details_json=details,
                created_at=created_at,
            )
        )

    def _stored_plan(self, row) -> StoredWorkflowPlan:
        return StoredWorkflowPlan(
            workflow_id=row["workflow_id"],
            request_text=row["request_text"],
            requester_role=row["requester_role"],
            team_name=row["team_name"],
            workflow_type=row["workflow_type"],
            summary=row["summary"],
            urgency=row["urgency"],
            steps=[WorkflowStep(**step) for step in row["steps_json"]],
            risks=row["risks_json"],
            missing_inputs=row["missing_inputs_json"],
            follow_up_questions=row["follow_up_questions_json"],
            success_checks=row["success_checks_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approval_status=row["approval_status"],
            decision_by=row["decision_by"],
            decision_note=row["decision_note"],
            decided_at=row["decided_at"],
        )

    @staticmethod
    def _workflow_evidence(row) -> WorkflowEvidence:
        evidence_id = row["evidence_id"]
        return WorkflowEvidence(
            evidence_id=evidence_id,
            citation_id=WorkflowStore._citation_id(evidence_id),
            workflow_id=row["workflow_id"],
            filename=row["filename"],
            media_type=row["media_type"],
            excerpt=row["excerpt"],
            source_sha256=row["source_sha256"],
            page_count=row["page_count"],
            character_count=row["character_count"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _citation_id(evidence_id: str) -> str:
        return f"SRC-{evidence_id.removeprefix('evi-')[:6].upper()}"

    def _step_status_counts(self, steps: list[WorkflowStep]) -> dict[str, int]:
        counts = {status: 0 for status in STEP_STATUSES}
        for step in steps:
            counts[step.status] = counts.get(step.status, 0) + 1
        return counts
