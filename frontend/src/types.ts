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

export interface WorkflowEvidence {
  evidence_id: string
  citation_id: string
  workflow_id: string
  filename: string
  media_type: string
  excerpt: string
  source_sha256: string
  page_count: number | null
  character_count: number
  created_at: string
}

export interface EvidenceSearchResult {
  chunk_id: string
  evidence_id: string
  citation_id: string
  filename: string
  chunk_index: number
  content: string
  retrieval_score: number
  rerank_score: number
  matched_terms: string[]
  relevance_label: string
  core_matches: string[]
}

export interface EvidenceSearchResponse {
  query: string
  strategy: RetrievalStrategy
  retriever: string
  index_backend: "sqlite" | null
  source_count: number
  total_chunks: number
  evidence_found: boolean
  latency_ms: number
  results: EvidenceSearchResult[]
  abstention_reason: string | null
  required_terms: string[]
}

export type GroundingStatus = "grounded" | "partial_evidence" | "insufficient_evidence"
export type RetrievalStrategy = "lexical" | "hybrid"

export interface GroundedAnswerClaim {
  claim_id: string
  text: string
  evidence_id: string
  citation_id: string
  filename: string
  chunk_id: string
  matched_terms: string[]
}

export interface GroundedAnswerResponse {
  query: string
  strategy: RetrievalStrategy
  retriever: string
  index_backend: "sqlite" | null
  status: GroundingStatus
  answer: string
  source_count: number
  total_chunks: number
  query_term_coverage: number
  latency_ms: number
  claims: GroundedAnswerClaim[]
  abstention_reason: string | null
  required_terms: string[]
  context_policy: "all_ranked" | "strong_only" | "strong_plus_supporting" | "supporting_only"
  excluded_result_count: number
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

export interface LatencyMetrics {
  sample_count: number
  p50: number
  p95: number
  maximum: number
}

export interface ServiceMetrics {
  service: string
  started_at: string
  uptime_seconds: number
  request_count: number
  server_error_count: number
  server_error_rate: number
  latency_ms: LatencyMetrics
}
