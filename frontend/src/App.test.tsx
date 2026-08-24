import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import App from "./App"
import type { ServiceMetrics, WorkflowEvidence, WorkflowPlan, WorkflowPlanListItem } from "./types"

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

const serviceMetrics: ServiceMetrics = {
  service: "workflow-copilot",
  started_at: "2026-08-15T13:00:00+00:00",
  uptime_seconds: 300,
  request_count: 42,
  server_error_count: 0,
  server_error_rate: 0,
  latency_ms: {
    sample_count: 42,
    p50: 7.2,
    p95: 18.4,
    maximum: 25.1,
  },
}

const sourceEvidence: WorkflowEvidence = {
  evidence_id: "evi-source-001",
  citation_id: "SRC-ABC123",
  workflow_id: pendingPlan.workflow_id,
  filename: "rollback-plan.txt",
  media_type: "text/plain",
  excerpt: "Rollback owner: Platform SRE. Verification window: 30 minutes.",
  source_sha256: "a".repeat(64),
  page_count: null,
  character_count: 62,
  created_at: "2026-08-15T13:05:00+00:00",
}

const evidenceSearch = {
  query: "rollback owner",
  strategy: "hybrid" as const,
  retriever: "deterministic_sqlite_persisted_hybrid_v1",
  index_backend: "sqlite" as const,
  source_count: 1,
  total_chunks: 1,
  evidence_found: true,
  latency_ms: 0.42,
  abstention_reason: null,
  required_terms: [],
  results: [
    {
      chunk_id: "evi-source-001-chunk-1",
      evidence_id: sourceEvidence.evidence_id,
      citation_id: sourceEvidence.citation_id,
      filename: sourceEvidence.filename,
      chunk_index: 0,
      content: sourceEvidence.excerpt,
      retrieval_score: 1.4,
      rerank_score: 2.2,
      matched_terms: ["rollback", "owner"],
      relevance_label: "strong",
      core_matches: ["rollback", "owner"],
    },
  ],
}

const groundedAnswer = {
  query: "rollback owner",
  strategy: "hybrid" as const,
  retriever: "deterministic_sqlite_persisted_hybrid_v1",
  index_backend: "sqlite" as const,
  status: "grounded" as const,
  answer: "The attached evidence supports these findings:\n- Rollback owner: Platform SRE. [SRC-ABC123]",
  source_count: 1,
  total_chunks: 1,
  query_term_coverage: 1,
  latency_ms: 0.58,
  abstention_reason: null,
  required_terms: [],
  context_policy: "strong_plus_supporting" as const,
  excluded_result_count: 0,
  claims: [
    {
      claim_id: "claim-1",
      text: "Rollback owner: Platform SRE.",
      evidence_id: sourceEvidence.evidence_id,
      citation_id: sourceEvidence.citation_id,
      filename: sourceEvidence.filename,
      chunk_id: "evi-source-001-chunk-1",
      matched_terms: ["rollback", "owner"],
    },
  ],
}

const supportingOnlyAnswer = {
  ...groundedAnswer,
  query: "customer support coverage",
  query_term_coverage: 0.67,
  context_policy: "supporting_only" as const,
  excluded_result_count: 2,
}

const abstainingSearch = {
  query: "Who authorized the emergency rollback?",
  strategy: "hybrid" as const,
  retriever: "deterministic_sqlite_persisted_hybrid_v1",
  index_backend: "sqlite" as const,
  source_count: 1,
  total_chunks: 1,
  evidence_found: false,
  latency_ms: 0.31,
  abstention_reason: "compound_intent_not_supported",
  required_terms: ["approval", "rollback"],
  context_policy: "all_ranked" as const,
  excluded_result_count: 0,
  results: [],
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
  cleanup()
  vi.restoreAllMocks()
})

describe("Workflow Copilot", () => {
  it("shows a useful empty state when there are no saved cases", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).endsWith("/metrics")) return jsonResponse(serviceMetrics)
      return jsonResponse([])
    })

    render(<App />)

    expect(await screen.findByText("No cases yet. Create the first one above.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Generate case plan" })).toBeEnabled()
    expect(screen.getByText("Create a case to open the review workspace.")).toBeInTheDocument()
    expect(screen.getByText("API connected")).toBeInTheDocument()
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("18ms")).toBeInTheDocument()
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

      if (url.endsWith("/metrics")) return jsonResponse(serviceMetrics)
      if (url.endsWith("/evidence")) return jsonResponse([sourceEvidence])

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
    expect(screen.getByText("SRC-ABC123")).toBeInTheDocument()
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
      if (url.endsWith("/metrics")) return jsonResponse(serviceMetrics)
      if (url.endsWith("/evidence")) return jsonResponse([sourceEvidence])
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

  it("uploads evidence and renders its stable citation", async () => {
    let attached = false
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? "GET"

      if (url.endsWith("/metrics")) return jsonResponse(serviceMetrics)
      if (url.endsWith("/evidence/answer")) return jsonResponse(groundedAnswer)
      if (url.endsWith("/evidence/search")) return jsonResponse(evidenceSearch)
      if (url.endsWith("/evidence") && method === "POST") {
        attached = true
        return jsonResponse(sourceEvidence)
      }
      if (url.endsWith("/evidence")) {
        return jsonResponse(attached ? [sourceEvidence] : [])
      }
      if (url.endsWith("/audit-events")) return jsonResponse([])
      if (url.endsWith(`/workflow/plans/${pendingPlan.workflow_id}`)) {
        return jsonResponse(pendingPlan)
      }
      if (url.endsWith("/workflow/plans")) return jsonResponse([listItem])
      throw new Error(`Unexpected request: ${method} ${url}`)
    })

    render(<App />)

    expect(await screen.findByText("No evidence attached yet.")).toBeInTheDocument()
    const file = new File(["Rollback owner: Platform SRE"], "rollback-plan.txt", {
      type: "text/plain",
    })
    await userEvent.upload(screen.getByLabelText("Evidence file"), file)
    await userEvent.click(screen.getByRole("button", { name: "Attach evidence" }))

    expect(await screen.findByText("SRC-ABC123")).toBeInTheDocument()
    expect(screen.getByText("rollback-plan.txt")).toBeInTheDocument()
    const uploadCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/evidence") && init?.method === "POST",
    )
    const form = uploadCall?.[1]?.body as FormData
    expect((form.get("file") as File).name).toBe("rollback-plan.txt")
    expect(form.get("actor")).toBe("Jordan Lee")

    await userEvent.clear(screen.getByLabelText("Find source evidence"))
    await userEvent.type(screen.getByLabelText("Find source evidence"), "rollback owner")
    await userEvent.click(screen.getByRole("button", { name: "Search evidence" }))

    expect(await screen.findByText(
      "Matched: rollback, owner · core: rollback, owner · score 2.20",
    )).toBeInTheDocument()
    expect(screen.getByText("Strong")).toBeInTheDocument()
    expect(screen.getByText("Hybrid · SQLite index · 1 chunks · 0.42 ms")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Draft grounded answer" }))

    expect(await screen.findByText("Grounded")).toBeInTheDocument()
    expect(screen.getByText((_content, element) => (
      element?.tagName === "P" && element.textContent === groundedAnswer.answer
    ))).toBeInTheDocument()
    expect(screen.getByText("Hybrid · SQLite index · 100% term coverage · 0.58 ms")).toBeInTheDocument()
    expect(screen.getByText(
      "Strong + complementary support · uncovered core concepts completed",
    )).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      `/workflow/plans/${pendingPlan.workflow_id}/evidence/answer`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          query: "rollback owner",
          strategy: "hybrid",
          top_k: 3,
          max_claims: 5,
        }),
      }),
    )
  })

  it("confirms evidence removal and clears the source from the case", async () => {
    let evidencePresent = true
    vi.spyOn(window, "confirm").mockReturnValue(true)
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? "GET"

      if (url.endsWith("/metrics")) return jsonResponse(serviceMetrics)
      if (
        url.endsWith(`/evidence/${sourceEvidence.evidence_id}`)
        && method === "DELETE"
      ) {
        evidencePresent = false
        return jsonResponse(sourceEvidence)
      }
      if (url.endsWith("/evidence")) {
        return jsonResponse(evidencePresent ? [sourceEvidence] : [])
      }
      if (url.endsWith("/audit-events")) return jsonResponse([])
      if (url.endsWith(`/workflow/plans/${pendingPlan.workflow_id}`)) {
        return jsonResponse(pendingPlan)
      }
      if (url.endsWith("/workflow/plans")) return jsonResponse([listItem])
      throw new Error(`Unexpected request: ${method} ${url}`)
    })

    render(<App />)

    expect(await screen.findByText("rollback-plan.txt")).toBeInTheDocument()
    await userEvent.click(
      screen.getByRole("button", { name: "Remove rollback-plan.txt" }),
    )

    expect(window.confirm).toHaveBeenCalledWith(
      "Remove rollback-plan.txt from this case?",
    )
    expect(await screen.findByText("No evidence attached yet.")).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      `/workflow/plans/${pendingPlan.workflow_id}/evidence/${sourceEvidence.evidence_id}`,
      expect.objectContaining({
        method: "DELETE",
        body: JSON.stringify({ actor: "Jordan Lee" }),
      }),
    )
  })

  it("explains hybrid abstention for unsupported compound intent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith("/metrics")) return jsonResponse(serviceMetrics)
      if (url.endsWith("/evidence/search")) return jsonResponse(abstainingSearch)
      if (url.endsWith("/evidence")) return jsonResponse([sourceEvidence])
      if (url.endsWith("/audit-events")) return jsonResponse([])
      if (url.endsWith(`/workflow/plans/${pendingPlan.workflow_id}`)) {
        return jsonResponse(pendingPlan)
      }
      if (url.endsWith("/workflow/plans")) return jsonResponse([listItem])
      throw new Error(`Unexpected request: ${url}`)
    })

    render(<App />)

    expect(await screen.findByRole("heading", { name: pendingPlan.summary })).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText("Find source evidence"))
    await userEvent.type(
      screen.getByLabelText("Find source evidence"),
      "Who authorized the emergency rollback?",
    )
    await userEvent.click(screen.getByRole("button", { name: "Search evidence" }))

    expect(await screen.findByText(
      "No single passage supports: approval + rollback. Ask for another source.",
    )).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      `/workflow/plans/${pendingPlan.workflow_id}/evidence/search`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          query: "Who authorized the emergency rollback?",
          strategy: "hybrid",
          top_k: 3,
        }),
      }),
    )
  })

  it("explains when weak results are excluded from supporting-only context", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith("/metrics")) return jsonResponse(serviceMetrics)
      if (url.endsWith("/evidence/answer")) return jsonResponse(supportingOnlyAnswer)
      if (url.endsWith("/evidence")) return jsonResponse([sourceEvidence])
      if (url.endsWith("/audit-events")) return jsonResponse([])
      if (url.endsWith(`/workflow/plans/${pendingPlan.workflow_id}`)) {
        return jsonResponse(pendingPlan)
      }
      if (url.endsWith("/workflow/plans")) return jsonResponse([listItem])
      throw new Error(`Unexpected request: ${url}`)
    })

    render(<App />)

    expect(await screen.findByRole("heading", { name: pendingPlan.summary })).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText("Find source evidence"))
    await userEvent.type(
      screen.getByLabelText("Find source evidence"),
      "customer support coverage",
    )
    await userEvent.click(screen.getByRole("button", { name: "Draft grounded answer" }))

    expect(await screen.findByText(
      "Supporting evidence only · 2 weak results excluded",
    )).toBeInTheDocument()
  })
})
