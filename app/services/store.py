from pathlib import Path
import json
import sqlite3

from app.schemas.models import StoredWorkflowPlan
from app.schemas.models import WorkflowPlanListItem
from app.schemas.models import WorkflowStep


class WorkflowStore:
    def __init__(self, database_path: str = "data/workflow_copilot.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

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
            "steps": [step.model_dump() for step in steps],
            "risks": risks,
            "missing_inputs": missing_inputs,
            "follow_up_questions": follow_up_questions,
            "success_checks": success_checks,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO workflow_plans (
                    workflow_id,
                    request_text,
                    requester_role,
                    team_name,
                    workflow_type,
                    summary,
                    urgency,
                    steps_json,
                    risks_json,
                    missing_inputs_json,
                    follow_up_questions_json,
                    success_checks_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["workflow_id"],
                    payload["request_text"],
                    payload["requester_role"],
                    payload["team_name"],
                    payload["workflow_type"],
                    payload["summary"],
                    payload["urgency"],
                    json.dumps(payload["steps"]),
                    json.dumps(payload["risks"]),
                    json.dumps(payload["missing_inputs"]),
                    json.dumps(payload["follow_up_questions"]),
                    json.dumps(payload["success_checks"]),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
        return StoredWorkflowPlan(**payload)

    def list_plans(self) -> list[WorkflowPlanListItem]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT workflow_id, workflow_type, summary, urgency, request_text, created_at, updated_at
                FROM workflow_plans
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
        return [
            WorkflowPlanListItem(
                workflow_id=row[0],
                workflow_type=row[1],
                summary=row[2],
                urgency=row[3],
                request_text=row[4],
                created_at=row[5],
                updated_at=row[6],
            )
            for row in rows
        ]

    def get_plan(self, workflow_id: str) -> StoredWorkflowPlan | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT workflow_id, request_text, requester_role, team_name, workflow_type, summary, urgency,
                       steps_json, risks_json, missing_inputs_json, follow_up_questions_json,
                       success_checks_json, created_at, updated_at
                FROM workflow_plans
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredWorkflowPlan(
            workflow_id=row[0],
            request_text=row[1],
            requester_role=row[2],
            team_name=row[3],
            workflow_type=row[4],
            summary=row[5],
            urgency=row[6],
            steps=[WorkflowStep(**step) for step in json.loads(row[7])],
            risks=json.loads(row[8]),
            missing_inputs=json.loads(row[9]),
            follow_up_questions=json.loads(row[10]),
            success_checks=json.loads(row[11]),
            created_at=row[12],
            updated_at=row[13],
        )

    def update_step_status(self, workflow_id: str, step_id: str, status: str, updated_at: str) -> StoredWorkflowPlan | None:
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
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                UPDATE workflow_plans
                SET steps_json = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (
                    json.dumps([step.model_dump() for step in updated_steps]),
                    updated_at,
                    workflow_id,
                ),
            )
        return plan.model_copy(update={"steps": updated_steps, "updated_at": updated_at})

    def _initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_plans (
                    workflow_id TEXT PRIMARY KEY,
                    request_text TEXT NOT NULL,
                    requester_role TEXT NOT NULL,
                    team_name TEXT,
                    workflow_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    risks_json TEXT NOT NULL,
                    missing_inputs_json TEXT NOT NULL,
                    follow_up_questions_json TEXT NOT NULL,
                    success_checks_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
