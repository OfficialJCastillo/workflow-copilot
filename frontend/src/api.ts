import type {
  ApprovalDecisionInput,
  CreatePlanInput,
  StepStatus,
  WorkflowAuditEvent,
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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(errorMessage(payload, `Request failed with status ${response.status}.`))
  }

  return response.json() as Promise<T>
}

export const workflowApi = {
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
}
