import type {
  ApprovalDecisionInput,
  CreatePlanInput,
  EvidenceSearchResponse,
  GroundedAnswerResponse,
  RetrievalStrategy,
  ServiceMetrics,
  StepStatus,
  WorkflowAuditEvent,
  WorkflowEvidence,
  WorkflowPlan,
  WorkflowPlanListItem,
} from "./types"

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")

function errorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === "string") return detail
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(errorMessage(payload, `Request failed with status ${response.status}.`))
  }

  return response.json() as Promise<T>
}

export const workflowApi = {
  getMetrics: () => request<ServiceMetrics>("/metrics"),

  listPlans: () => request<WorkflowPlanListItem[]>("/workflow/plans"),

  getPlan: (workflowId: string) =>
    request<WorkflowPlan>(`/workflow/plans/${workflowId}`),

  createPlan: (input: CreatePlanInput) =>
    request<WorkflowPlan>("/workflow/plans", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  updateStep: (
    workflowId: string,
    stepId: string,
    status: StepStatus,
    actor: string,
  ) =>
    request<WorkflowPlan>(`/workflow/plans/${workflowId}/steps/${stepId}`, {
      method: "PATCH",
      body: JSON.stringify({ status, actor }),
    }),

  submitForApproval: (workflowId: string, actor: string) =>
    request<WorkflowPlan>(`/workflow/plans/${workflowId}/approval-requests`, {
      method: "POST",
      body: JSON.stringify({ actor }),
    }),

  decidePlan: (workflowId: string, input: ApprovalDecisionInput) =>
    request<WorkflowPlan>(`/workflow/plans/${workflowId}/approval-decisions`, {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listAuditEvents: (workflowId: string) =>
    request<WorkflowAuditEvent[]>(`/workflow/plans/${workflowId}/audit-events`),

  listEvidence: (workflowId: string) =>
    request<WorkflowEvidence[]>(`/workflow/plans/${workflowId}/evidence`),

  attachEvidence: (workflowId: string, file: File, actor: string) => {
    const body = new FormData()
    body.append("file", file)
    body.append("actor", actor)
    return request<WorkflowEvidence>(`/workflow/plans/${workflowId}/evidence`, {
      method: "POST",
      body,
    })
  },

  deleteEvidence: (workflowId: string, evidenceId: string, actor: string) =>
    request<WorkflowEvidence>(
      `/workflow/plans/${workflowId}/evidence/${evidenceId}`,
      {
        method: "DELETE",
        body: JSON.stringify({ actor }),
      },
    ),

  searchEvidence: (
    workflowId: string,
    query: string,
    strategy: RetrievalStrategy = "lexical",
    topK = 3,
  ) =>
    request<EvidenceSearchResponse>(`/workflow/plans/${workflowId}/evidence/search`, {
      method: "POST",
      body: JSON.stringify({ query, strategy, top_k: topK }),
    }),

  answerFromEvidence: (
    workflowId: string,
    query: string,
    strategy: RetrievalStrategy = "lexical",
    topK = 3,
    maxClaims = 5,
  ) =>
    request<GroundedAnswerResponse>(`/workflow/plans/${workflowId}/evidence/answer`, {
      method: "POST",
      body: JSON.stringify({ query, strategy, top_k: topK, max_claims: maxClaims }),
    }),
}
