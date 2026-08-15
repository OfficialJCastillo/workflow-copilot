import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import App from "./App"
import type { WorkflowPlan, WorkflowPlanListItem } from "./types"

const pendingPlan: WorkflowPlan = {
  workflow_id: "wf-review-001",
  workflow_type: "release_preparation",
  summary: "Prepare a controlled customer-facing release.",
  urgency: "high",
  request_text: "Prepare the customer-facing API release next Thursday.",
  requester_role: "release lead",
  team_name: "Platform Operations",
  steps: [
    {
      step_id: "step-1",
      title: "Confirm release scope",
      owner: "release lead",
      status: "completed",
      rationale: "A stable scope makes the approval decision reviewable.",
    },
  ],
  risks: ["Rollback criteria are incomplete."],
  missing_inputs: ["Deployment window"],
  follow_up_questions: ["Who is the final reviewer?"],
  success_checks: ["Stakeholders receive the release notice."],
  created_at: "2026-08-15T13:00:00+00:00",
  updated_at: "2026-08-15T13:10:00+00:00",
  approval_status: "pending_approval",
  decision_by: null,
  decision_note: null,
  decided_at: null,
}

const listItem: WorkflowPlanListItem = {
  workflow_id: pendingPlan.workflow_id,
  workflow_type: pendingPlan.workflow_type,
  summary: pendingPlan.summary,
  urgency: pendingPlan.urgency,
  request_text: pendingPlan.request_text,
  step_status_counts: { completed: 1 },
  completed_step_count: 1,
  total_step_count: 1,
  approval_status: "pending_approval",
  created_at: pendingPlan.created_at,
  updated_at: pendingPlan.updated_at,
}

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response
}

function errorResponse(status: number, detail: string): Response {
  return {
    ok: false,
    status,
    json: async () => ({ detail }),
  } as Response
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("Workflow Copilot", () => {
  it("shows a useful empty state when there are no saved cases", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]))

    render(<App />)

    expect(await screen.findByText("No cases yet. Create the first one above.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Generate case plan" })).toBeEnabled()
    expect(screen.getByText("Create a case to open the review workspace.")).toBeInTheDocument()
    expect(screen.getByText("API connected")).toBeInTheDocument()
  })

  it("reports when the API is unavailable during startup", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errorResponse(503, "Database is unavailable."))

    render(<App />)

    expect(await screen.findByText("API unavailable")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("Database is unavailable.")
  })

  it("loads a pending case and records an approval decision", async () => {
    let approved = false
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? "GET"

      if (url.endsWith("/approval-decisions") && method === "POST") {
        approved = true
        return jsonResponse({
          ...pendingPlan,
          approval_status: "approved",
          decision_by: "Jordan Lee",
          decision_note: "Ready for handoff.",
          decided_at: "2026-08-15T13:15:00+00:00",
        })
      }
      if (url.endsWith("/audit-events")) {
        return jsonResponse([
          {
            event_id: approved ? "event-2" : "event-1",
            workflow_id: pendingPlan.workflow_id,
            event_type: approved ? "approval_decided" : "approval_requested",
            actor: "Jordan Lee",
            details: approved ? { decision: "approved" } : {},
            created_at: "2026-08-15T13:15:00+00:00",
          },
        ])
      }
      if (url.endsWith(`/workflow/plans/${pendingPlan.workflow_id}`)) {
        return jsonResponse(pendingPlan)
      }
      if (url.endsWith("/workflow/plans")) {
        return jsonResponse([
          approved ? { ...listItem, approval_status: "approved" } : listItem,
        ])
      }
      throw new Error(`Unexpected request: ${method} ${url}`)
    })

    render(<App />)

    expect(await screen.findByRole("heading", { name: pendingPlan.summary })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText("Decision note"), "Ready for handoff.")
    await userEvent.click(screen.getByRole("button", { name: "Approve plan" }))

    expect(await screen.findByText("Cleared for controlled handoff")).toBeInTheDocument()
    expect(screen.getByText("Approved by Jordan Lee")).toBeInTheDocument()
    expect(screen.getByText("Ready for handoff.")).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/workflow/plans/${pendingPlan.workflow_id}/approval-decisions`,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            actor: "Jordan Lee",
            decision: "approved",
            note: "Ready for handoff.",
          }),
        }),
      )
    })
  })

  it("shows a rejected decision before allowing resubmission", async () => {
    const rejectedPlan: WorkflowPlan = {
      ...pendingPlan,
      approval_status: "rejected",
      decision_by: "Security Reviewer",
      decision_note: "Rollback ownership is missing.",
      decided_at: "2026-08-15T13:15:00+00:00",
    }
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith("/audit-events")) return jsonResponse([])
      if (url.endsWith(`/workflow/plans/${pendingPlan.workflow_id}`)) {
        return jsonResponse(rejectedPlan)
      }
      if (url.endsWith("/workflow/plans")) {
        return jsonResponse([{ ...listItem, approval_status: "rejected" }])
      }
      throw new Error(`Unexpected request: ${url}`)
    })

    render(<App />)

    expect(await screen.findByText("Revision requested")).toBeInTheDocument()
    expect(screen.getByText("Rejected by Security Reviewer")).toBeInTheDocument()
    expect(screen.getByText("Rollback ownership is missing.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeEnabled()
  })
})
