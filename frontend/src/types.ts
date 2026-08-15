export type ApprovalStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "rejected"

export type StepStatus = "pending" | "in_progress" | "completed" | "blocked"

export interface WorkflowStep {
  step_id: string
  title: string
  owner: string
  status: StepStatus
  rationale: string
}

export interface WorkflowPlan {
  workflow_id: string
  workflow_type: string
  summary: string
  urgency: string
  request_text: string
  requester_role: string
  team_name: string | null
  steps: WorkflowStep[]
  risks: string[]
  missing_inputs: string[]
  follow_up_questions: string[]
  success_checks: string[]
  created_at: string
  updated_at: string
  approval_status: ApprovalStatus
  decision_by: string | null
  decision_note: string | null
  decided_at: string | null
}

export interface WorkflowPlanListItem {
  workflow_id: string
  workflow_type: string
  summary: string
  urgency: string
  request_text: string
  step_status_counts: Record<string, number>
  completed_step_count: number
  total_step_count: number
  approval_status: ApprovalStatus
  created_at: string
  updated_at: string
}

export interface WorkflowAuditEvent {
  event_id: string
  workflow_id: string
  event_type: string
  actor: string
  details: Record<string, string>
  created_at: string
}

export interface CreatePlanInput {
  request_text: string
  requester_role: string
  team_name: string | null
}

export interface ApprovalDecisionInput {
  actor: string
  decision: "approved" | "rejected"
  note: string | null
}
