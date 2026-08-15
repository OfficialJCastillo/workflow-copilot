import { useEffect, useMemo, useState } from "react"
import type { FormEvent } from "react"
import { workflowApi } from "./api"
import type {
  ApprovalStatus,
  StepStatus,
  WorkflowAuditEvent,
  WorkflowPlan,
  WorkflowPlanListItem,
} from "./types"
import "./index.css"

const DEFAULT_REQUEST =
  "Prepare a customer-facing API release next Thursday with rollback readiness and stakeholder approval."

const statusLabels: Record<ApprovalStatus, string> = {
  draft: "Draft",
  pending_approval: "Awaiting approval",
  approved: "Approved",
  rejected: "Needs revision",
}

const stepStatusLabels: Record<StepStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Complete",
  blocked: "Blocked",
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value))
}

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function StatusPill({ status }: { status: ApprovalStatus }) {
  return <span className={`status-pill status-${status}`}>{statusLabels[status]}</span>
}

function EmptyList({ children }: { children: string }) {
  return <p className="empty-list">{children}</p>
}

export default function App() {
  const [plans, setPlans] = useState<WorkflowPlanListItem[]>([])
  const [selectedPlan, setSelectedPlan] = useState<WorkflowPlan | null>(null)
  const [auditEvents, setAuditEvents] = useState<WorkflowAuditEvent[]>([])
  const [requestText, setRequestText] = useState(DEFAULT_REQUEST)
  const [requesterRole, setRequesterRole] = useState("release lead")
  const [teamName, setTeamName] = useState("Platform Operations")
  const [actor, setActor] = useState("Jordan Lee")
  const [decisionNote, setDecisionNote] = useState("")
  const [loading, setLoading] = useState(true)
  const [apiAvailable, setApiAvailable] = useState<boolean | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const metrics = useMemo(
    () => ({
      total: plans.length,
      review: plans.filter((plan) => plan.approval_status === "pending_approval").length,
      approved: plans.filter((plan) => plan.approval_status === "approved").length,
    }),
    [plans],
  )

  async function loadPlan(workflowId: string) {
    setBusyAction("select")
    setError(null)
    try {
      const [plan, events] = await Promise.all([
        workflowApi.getPlan(workflowId),
        workflowApi.listAuditEvents(workflowId),
      ])
      setSelectedPlan(plan)
      setAuditEvents(events)
      setDecisionNote("")
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load the case.")
    } finally {
      setBusyAction(null)
    }
  }

  async function refreshPlans() {
    const refreshedPlans = await workflowApi.listPlans()
    setPlans(refreshedPlans)
    return refreshedPlans
  }

  useEffect(() => {
    let active = true

    async function initialize() {
      setLoading(true)
      setError(null)
      try {
        const initialPlans = await workflowApi.listPlans()
        if (!active) return
        setPlans(initialPlans)
        setApiAvailable(true)
        if (initialPlans.length > 0) {
          const [plan, events] = await Promise.all([
            workflowApi.getPlan(initialPlans[0].workflow_id),
            workflowApi.listAuditEvents(initialPlans[0].workflow_id),
          ])
          if (!active) return
          setSelectedPlan(plan)
          setAuditEvents(events)
        }
      } catch (loadError) {
        if (active) {
          setApiAvailable(false)
          setError(
            loadError instanceof Error ? loadError.message : "Unable to connect to the workflow API.",
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    void initialize()
    return () => {
      active = false
    }
  }, [])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusyAction("create")
    setError(null)
    try {
      const plan = await workflowApi.createPlan({
        request_text: requestText.trim(),
        requester_role: requesterRole.trim() || "requester",
        team_name: teamName.trim() || null,
      })
      const [events] = await Promise.all([
        workflowApi.listAuditEvents(plan.workflow_id),
        refreshPlans(),
      ])
      setSelectedPlan(plan)
      setAuditEvents(events)
      setDecisionNote("")
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create the case.")
    } finally {
      setBusyAction(null)
    }
  }

  async function applyPlanAction(
    action: string,
    operation: () => Promise<WorkflowPlan>,
  ) {
    if (!selectedPlan) return
    setBusyAction(action)
    setError(null)
    try {
      const plan = await operation()
      const [events] = await Promise.all([
        workflowApi.listAuditEvents(plan.workflow_id),
        refreshPlans(),
      ])
      setSelectedPlan(plan)
      setAuditEvents(events)
      setDecisionNote("")
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "The workflow action failed.")
    } finally {
      setBusyAction(null)
    }
  }

  function updateStep(stepId: string, status: StepStatus) {
    if (!selectedPlan) return
    void applyPlanAction(`step-${stepId}-${status}`, () =>
      workflowApi.updateStep(selectedPlan.workflow_id, stepId, status, actor.trim()),
    )
  }

  function submitForApproval() {
    if (!selectedPlan) return
    void applyPlanAction("submit", () =>
      workflowApi.submitForApproval(selectedPlan.workflow_id, actor.trim()),
    )
  }

  function decide(decision: "approved" | "rejected") {
    if (!selectedPlan) return
    void applyPlanAction(decision, () =>
      workflowApi.decidePlan(selectedPlan.workflow_id, {
        actor: actor.trim(),
        decision,
        note: decisionNote.trim() || null,
      }),
    )
  }

  const completedSteps = selectedPlan?.steps.filter((step) => step.status === "completed").length ?? 0
  const progress = selectedPlan?.steps.length
    ? Math.round((completedSteps / selectedPlan.steps.length) * 100)
    : 0
  const apiStatus = apiAvailable === null
    ? "Checking API"
    : apiAvailable
      ? "API connected"
      : "API unavailable"

  return (
    <div className="app-frame">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">WC</div>
          <div>
            <p className="eyebrow">Operations control plane</p>
            <h1>Workflow Copilot</h1>
          </div>
        </div>
        <div className={`system-status ${apiAvailable === false ? "system-status-unavailable" : ""}`}>
          <span className="status-dot" aria-hidden="true" />
          {apiStatus}
        </div>
      </header>

      <section className="command-strip" aria-label="Portfolio summary">
        <div>
          <p className="eyebrow">Case portfolio</p>
          <h2>Turn ambiguous work into accountable execution.</h2>
        </div>
        <div className="metrics">
          <div><strong>{metrics.total}</strong><span>Total cases</span></div>
          <div><strong>{metrics.review}</strong><span>In review</span></div>
          <div><strong>{metrics.approved}</strong><span>Approved</span></div>
        </div>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          <strong>Action needed</strong>
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button>
        </div>
      )}

      <main className="workspace">
        <aside className="case-sidebar">
          <section className="panel new-case-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Intake</p>
                <h2>Create a case</h2>
              </div>
              <span className="step-number">01</span>
            </div>
            <form onSubmit={handleCreate}>
              <label htmlFor="request-text">Operational request</label>
              <textarea
                id="request-text"
                value={requestText}
                onChange={(event) => setRequestText(event.target.value)}
                minLength={8}
                required
              />
              <div className="input-row">
                <div>
                  <label htmlFor="requester-role">Requester role</label>
                  <input
                    id="requester-role"
                    value={requesterRole}
                    onChange={(event) => setRequesterRole(event.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="team-name">Team</label>
                  <input
                    id="team-name"
                    value={teamName}
                    onChange={(event) => setTeamName(event.target.value)}
                  />
                </div>
              </div>
              <button className="primary-button full-width" disabled={busyAction === "create"}>
                {busyAction === "create" ? "Structuring case…" : "Generate case plan"}
              </button>
            </form>
          </section>

          <section className="panel case-list-panel">
            <div className="panel-heading compact">
              <div>
                <p className="eyebrow">Queue</p>
                <h2>Recent cases</h2>
              </div>
              <span className="count-badge">{plans.length}</span>
            </div>
            <div className="case-list" aria-live="polite">
              {loading && <EmptyList>Loading cases…</EmptyList>}
              {!loading && plans.length === 0 && <EmptyList>No cases yet. Create the first one above.</EmptyList>}
              {plans.map((plan) => (
                <button
                  type="button"
                  className={`case-card ${selectedPlan?.workflow_id === plan.workflow_id ? "selected" : ""}`}
                  key={plan.workflow_id}
                  onClick={() => void loadPlan(plan.workflow_id)}
                  aria-pressed={selectedPlan?.workflow_id === plan.workflow_id}
                >
                  <span className="case-card-topline">
                    <span>{titleCase(plan.workflow_type)}</span>
                    <StatusPill status={plan.approval_status} />
                  </span>
                  <strong>{plan.summary}</strong>
                  <span className="case-card-meta">
                    {plan.completed_step_count}/{plan.total_step_count} steps · {formatDate(plan.updated_at)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        </aside>

        <section className="case-workbench" aria-busy={busyAction === "select"}>
          {!selectedPlan ? (
            <div className="panel empty-state">
              <span className="empty-state-index">01 → 02 → 03</span>
              <h2>Create a case to open the review workspace.</h2>
              <p>The copilot will surface a proposed plan, operational risks, missing inputs, approval controls, and an audit trail.</p>
            </div>
          ) : (
            <>
              <section className="panel case-hero">
                <div className="case-hero-heading">
                  <div>
                    <div className="hero-labels">
                      <StatusPill status={selectedPlan.approval_status} />
                      <span>{titleCase(selectedPlan.workflow_type)}</span>
                      <span>{titleCase(selectedPlan.urgency)} urgency</span>
                    </div>
                    <h2>{selectedPlan.summary}</h2>
                    <p className="request-quote">“{selectedPlan.request_text}”</p>
                  </div>
                  <div className="case-id">
                    <span>Case ID</span>
                    <code>{selectedPlan.workflow_id}</code>
                  </div>
                </div>
                <div className="progress-block">
                  <div>
                    <span>Execution readiness</span>
                    <strong>{completedSteps} of {selectedPlan.steps.length} steps complete</strong>
                  </div>
                  <span>{progress}%</span>
                </div>
                <div className="progress-track" aria-label={`${progress}% complete`}>
                  <span style={{ width: `${progress}%` }} />
                </div>
              </section>

              <div className="detail-grid">
                <section className="panel execution-panel">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">Execution plan</p>
                      <h2>Owned next steps</h2>
                    </div>
                    <span className="step-number">02</span>
                  </div>
                  <div className="step-list">
                    {selectedPlan.steps.map((step, index) => (
                      <article className="workflow-step" key={step.step_id}>
                        <span className="workflow-step-index">{String(index + 1).padStart(2, "0")}</span>
                        <div className="workflow-step-body">
                          <div className="workflow-step-title">
                            <div>
                              <h3>{step.title}</h3>
                              <p>{step.rationale}</p>
                            </div>
                            <span className={`step-status step-${step.status}`}>{stepStatusLabels[step.status]}</span>
                          </div>
                          <div className="workflow-step-footer">
                            <span>Owner · <strong>{step.owner}</strong></span>
                            <div className="step-actions">
                              {step.status !== "in_progress" && step.status !== "completed" && (
                                <button
                                  type="button"
                                  className="text-button"
                                  disabled={!actor.trim() || busyAction !== null}
                                  onClick={() => updateStep(step.step_id, "in_progress")}
                                >
                                  Start
                                </button>
                              )}
                              {step.status !== "completed" && (
                                <button
                                  type="button"
                                  className="text-button"
                                  disabled={!actor.trim() || busyAction !== null}
                                  onClick={() => updateStep(step.step_id, "completed")}
                                >
                                  Mark complete
                                </button>
                              )}
                              {step.status === "completed" && (
                                <button
                                  type="button"
                                  className="text-button"
                                  disabled={!actor.trim() || busyAction !== null}
                                  onClick={() => updateStep(step.step_id, "pending")}
                                >
                                  Reopen
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>

                <aside className="right-rail">
                  <section className="panel approval-panel">
                    <div className="panel-heading compact">
                      <div>
                        <p className="eyebrow">Human checkpoint</p>
                        <h2>Approval</h2>
                      </div>
                      <span className="step-number">03</span>
                    </div>
                    <label htmlFor="actor">Acting as</label>
                    <input
                      id="actor"
                      value={actor}
                      onChange={(event) => setActor(event.target.value)}
                      placeholder="Reviewer name"
                      required
                    />

                    {(selectedPlan.approval_status === "draft" || selectedPlan.approval_status === "rejected") && (
                      <div className="approval-action">
                        {selectedPlan.approval_status === "rejected" && (
                          <div className="decision-summary rejected-summary">
                            <strong>Revision requested</strong>
                            <span>Rejected by {selectedPlan.decision_by}</span>
                            {selectedPlan.decision_note && <p>{selectedPlan.decision_note}</p>}
                          </div>
                        )}
                        <p>Submit this plan to lock in an accountable review decision.</p>
                        <button
                          type="button"
                          className="primary-button full-width"
                          disabled={!actor.trim() || busyAction !== null}
                          onClick={submitForApproval}
                        >
                          {busyAction === "submit" ? "Submitting…" : "Submit for approval"}
                        </button>
                      </div>
                    )}

                    {selectedPlan.approval_status === "pending_approval" && (
                      <div className="approval-action">
                        <label htmlFor="decision-note">Decision note</label>
                        <textarea
                          id="decision-note"
                          value={decisionNote}
                          onChange={(event) => setDecisionNote(event.target.value)}
                          placeholder="Add context; required when rejecting."
                        />
                        <div className="decision-buttons">
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={!actor.trim() || !decisionNote.trim() || busyAction !== null}
                            onClick={() => decide("rejected")}
                          >
                            Reject with note
                          </button>
                          <button
                            type="button"
                            className="primary-button"
                            disabled={!actor.trim() || busyAction !== null}
                            onClick={() => decide("approved")}
                          >
                            {busyAction === "approved" ? "Approving…" : "Approve plan"}
                          </button>
                        </div>
                      </div>
                    )}

                    {selectedPlan.approval_status === "approved" && (
                      <div className="decision-summary approved-summary">
                        <strong>Cleared for controlled handoff</strong>
                        <span>Approved by {selectedPlan.decision_by}</span>
                        {selectedPlan.decision_note && <p>{selectedPlan.decision_note}</p>}
                      </div>
                    )}
                  </section>

                  <section className="panel signal-panel">
                    <p className="eyebrow">Review signals</p>
                    <h2>Risks & gaps</h2>
                    <div className="signal-group risk-group">
                      <h3>Risks</h3>
                      {selectedPlan.risks.length ? (
                        <ul>{selectedPlan.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul>
                      ) : <EmptyList>No risks detected.</EmptyList>}
                    </div>
                    <div className="signal-group">
                      <h3>Missing inputs</h3>
                      {selectedPlan.missing_inputs.length ? (
                        <ul>{selectedPlan.missing_inputs.map((input) => <li key={input}>{input}</li>)}</ul>
                      ) : <EmptyList>No missing inputs.</EmptyList>}
                    </div>
                  </section>
                </aside>
              </div>

              <div className="lower-grid">
                <section className="panel checklist-panel">
                  <p className="eyebrow">Quality gate</p>
                  <h2>Success checks</h2>
                  {selectedPlan.success_checks.length ? (
                    <ul className="check-list">
                      {selectedPlan.success_checks.map((check) => <li key={check}>{check}</li>)}
                    </ul>
                  ) : <EmptyList>No checks generated.</EmptyList>}
                  {selectedPlan.follow_up_questions.length > 0 && (
                    <>
                      <h3 className="subheading">Follow-up questions</h3>
                      <ul className="question-list">
                        {selectedPlan.follow_up_questions.map((question) => <li key={question}>{question}</li>)}
                      </ul>
                    </>
                  )}
                </section>

                <section className="panel audit-panel">
                  <div className="panel-heading compact">
                    <div>
                      <p className="eyebrow">System record</p>
                      <h2>Audit trail</h2>
                    </div>
                    <span className="count-badge">{auditEvents.length}</span>
                  </div>
                  {auditEvents.length === 0 ? <EmptyList>No events recorded.</EmptyList> : (
                    <ol className="audit-list">
                      {auditEvents.map((auditEvent) => (
                        <li key={auditEvent.event_id}>
                          <span className="audit-marker" aria-hidden="true" />
                          <div>
                            <div className="audit-title">
                              <strong>{titleCase(auditEvent.event_type)}</strong>
                              <time>{formatDate(auditEvent.created_at)}</time>
                            </div>
                            <p>Actor · {auditEvent.actor}</p>
                            {Object.keys(auditEvent.details).length > 0 && (
                              <p className="audit-details">
                                {Object.entries(auditEvent.details)
                                  .map(([key, value]) => `${titleCase(key)}: ${value}`)
                                  .join(" · ")}
                              </p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
