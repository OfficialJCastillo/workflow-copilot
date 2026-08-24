from fastapi.responses import HTMLResponse


def render_demo_ui() -> HTMLResponse:
    return HTMLResponse(
        """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>workflow-copilot demo UI</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4efe7;
      --panel: #fffdf8;
      --panel-alt: #f6f1e8;
      --text: #1e1d1a;
      --muted: #645f56;
      --accent: #0f766e;
      --accent-soft: #d7f1ec;
      --border: #d8cfc0;
      --warn: #8a4b10;
      --shadow: 0 20px 40px rgba(43, 37, 28, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 28%),
        linear-gradient(180deg, #fbf7f0 0%, var(--bg) 100%);
      color: var(--text);
    }

    .page {
      max-width: 1180px;
      margin: 0 auto;
      padding: 48px 20px 64px;
    }

    .hero {
      display: grid;
      gap: 12px;
      margin-bottom: 28px;
    }

    .eyebrow {
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
    }

    h1 {
      margin: 0;
      font-size: clamp(2.2rem, 4vw, 4rem);
      line-height: 0.95;
      max-width: 10ch;
    }

    .subtitle {
      margin: 0;
      max-width: 66ch;
      font-size: 1.08rem;
      line-height: 1.5;
      color: var(--muted);
    }

    .layout {
      display: grid;
      gap: 20px;
      grid-template-columns: minmax(320px, 400px) minmax(0, 1fr);
      align-items: start;
    }

    .panel {
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(10px);
    }

    .panel-body,
    .result-header,
    .saved-header {
      padding: 24px;
      display: grid;
      gap: 14px;
    }

    .panel-body {
      gap: 18px;
    }

    .form-copy,
    .result-copy,
    .saved-copy {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }

    label {
      display: grid;
      gap: 8px;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.92rem;
      font-weight: 700;
    }

    textarea,
    input {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px 16px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
      font-size: 1rem;
    }

    textarea {
      min-height: 180px;
      resize: vertical;
      line-height: 1.45;
    }

    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }

    button {
      appearance: none;
      border: 0;
      border-radius: 999px;
      padding: 14px 18px;
      background: linear-gradient(135deg, #0f766e 0%, #155e75 100%);
      color: white;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.98rem;
      font-weight: 700;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease;
      box-shadow: 0 16px 30px rgba(21, 94, 117, 0.18);
    }

    button.secondary {
      background: white;
      color: var(--text);
      border: 1px solid var(--border);
      box-shadow: none;
    }

    button.danger {
      background: linear-gradient(135deg, #be123c 0%, #881337 100%);
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.65; cursor: wait; transform: none; }

    .status {
      margin: 0;
      min-height: 1.25rem;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      color: var(--muted);
    }

    .status.error { color: #9f1239; }

    .section-divider {
      border-top: 1px solid var(--border);
    }

    .result-header h2,
    .saved-header h2 {
      margin: 0;
      font-size: 1.55rem;
    }

    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #124b45;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.9rem;
      font-weight: 700;
    }

    .result-grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      padding: 24px;
    }

    .card {
      border-radius: 18px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-alt) 100%);
      padding: 18px;
      display: grid;
      gap: 14px;
    }

    .card.full {
      grid-column: 1 / -1;
    }

    .card h3 {
      margin: 0;
      font-size: 1rem;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }

    .approval-copy {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }

    .audit-list {
      list-style: none;
      padding: 0;
    }

    .audit-list li {
      display: grid;
      gap: 4px;
      border-left: 3px solid #9fcfc8;
      padding-left: 12px;
    }

    .audit-meta {
      color: var(--muted);
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.84rem;
    }

    .placeholder,
    .saved-empty {
      padding: 24px;
      color: var(--muted);
      line-height: 1.55;
    }

    .empty-state {
      border: 1px dashed var(--border);
      border-radius: 18px;
      padding: 20px;
      background: rgba(255, 255, 255, 0.5);
    }

    ol,
    ul {
      margin: 0;
      padding-left: 20px;
      display: grid;
      gap: 12px;
    }

    li {
      line-height: 1.45;
    }

    .step-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 6px;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.86rem;
      color: var(--muted);
    }

    .step-chip {
      border-radius: 999px;
      padding: 4px 10px;
      background: rgba(15, 118, 110, 0.1);
    }

    .saved-list {
      display: grid;
      gap: 12px;
      padding: 0 24px 24px;
    }

    .saved-item {
      width: 100%;
      text-align: left;
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 14px 16px;
      background: rgba(255, 255, 255, 0.55);
      color: var(--text);
      box-shadow: none;
    }

    .saved-item.active {
      border-color: #9fcfc8;
      background: rgba(215, 241, 236, 0.55);
    }

    .saved-item:hover {
      transform: none;
      border-color: #b8b0a1;
    }

    .saved-item-title {
      margin: 0 0 6px;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.95rem;
      font-weight: 700;
    }

    .saved-item-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      font-size: 0.83rem;
    }

    .saved-item-progress {
      margin-top: 10px;
      display: grid;
      gap: 6px;
    }

    .progress-track {
      height: 8px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.12);
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(135deg, #0f766e 0%, #155e75 100%);
    }

    .hint {
      margin: 0;
      color: var(--warn);
      font-size: 0.94rem;
      line-height: 1.45;
    }

    @media (max-width: 900px) {
      .layout,
      .result-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">Structured planning before automation</p>
      <h1>workflow-copilot demo UI</h1>
      <p class="subtitle">
        Try the deterministic planning engine in one screen. Paste an operational request, add the requester role and team,
        save the generated workflow, and move it through a human approval flow with a visible audit trail.
      </p>
    </section>

    <section class="layout">
      <form class="panel" id="plan-form">
        <div class="panel-body">
          <p class="form-copy">
            This demo uses the existing planning and persistence endpoints. You can preview a plan from
            <code>POST /workflow/plan</code> or save it through <code>POST /workflow/plans</code>.
          </p>

          <label>
            Task request
            <textarea id="request-text" name="request_text" required>Prepare a customer-facing API release ASAP for next quarter and confirm who signs off.</textarea>
          </label>

          <label>
            Requester role
            <input id="requester-role" name="requester_role" value="engineering_manager" />
          </label>

          <label>
            Team name
            <input id="team-name" name="team_name" value="Platform" />
          </label>

          <label>
            Acting user
            <input id="actor-name" name="actor_name" value="Jorge Castillo" />
          </label>

          <div class="button-row">
            <button type="submit" id="submit-button">Generate workflow plan</button>
            <button type="button" id="save-button" class="secondary">Save plan</button>
          </div>
          <p class="status" id="status-text" aria-live="polite"></p>
        </div>
      </form>

      <section class="panel">
        <div class="result-header">
          <h2>Plan preview</h2>
          <p class="result-copy">
            The right panel updates with the structured plan response so reviewers can understand the product without reaching for Postman.
          </p>
        </div>
        <div id="results-root" class="placeholder">
          <div class="empty-state">
            Submit a request to see steps, risks, missing inputs, follow-up questions, and success checks rendered here.
          </div>
        </div>

        <div class="section-divider"></div>

        <div class="saved-header">
          <h2>Recent saved plans</h2>
          <p class="saved-copy">
            Save a plan to the local SQLite store, then reopen it here to make the persistence layer visible in the demo.
          </p>
        </div>
        <div id="saved-plans-root" class="saved-empty">
          <div class="empty-state">
            No saved plans yet. Use the save button to create one from the current request.
          </div>
        </div>
      </section>
    </section>
  </main>

  <script>
    const form = document.getElementById("plan-form");
    const statusText = document.getElementById("status-text");
    const submitButton = document.getElementById("submit-button");
    const saveButton = document.getElementById("save-button");
    const resultsRoot = document.getElementById("results-root");
    const savedPlansRoot = document.getElementById("saved-plans-root");

    let activeSavedWorkflowId = null;

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function buildPayload() {
      return {
        request_text: document.getElementById("request-text").value,
        requester_role: document.getElementById("requester-role").value || "requester",
        team_name: document.getElementById("team-name").value || null,
      };
    }

    function renderList(items, ordered = false) {
      if (!items || items.length === 0) {
        return '<p class="hint">No items returned for this section.</p>';
      }

      const tag = ordered ? "ol" : "ul";
      return `<${tag}>${items.join("")}</${tag}>`;
    }

    function formatTimestamp(value) {
      if (!value) {
        return null;
      }

      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) {
        return value;
      }

      return parsed.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    }

    function humanize(value) {
      return String(value || "").replaceAll("_", " ");
    }

    function renderApprovalControls(data) {
      if (!data.workflow_id || !data.approval_status) {
        return "";
      }

      let actions = "";
      if (data.approval_status === "draft" || data.approval_status === "rejected") {
        actions = '<button type="button" data-approval-action="submit">Submit for approval</button>';
      } else if (data.approval_status === "pending_approval") {
        actions = `
          <label>
            Decision note
            <input id="decision-note" name="decision_note" placeholder="Required when rejecting; optional when approving" />
          </label>
          <button type="button" data-approval-action="approved">Approve plan</button>
          <button type="button" class="danger" data-approval-action="rejected">Reject plan</button>
        `;
      }

      const decision = data.decision_by
        ? `<p class="approval-copy">Last decision by <strong>${escapeHtml(data.decision_by)}</strong>${data.decision_note ? ` — ${escapeHtml(data.decision_note)}` : ""}</p>`
        : '<p class="approval-copy">No approval decision has been recorded.</p>';

      return `
        <section class="card full">
          <h3>Human approval</h3>
          <div class="badges">
            <span class="badge">Status: ${escapeHtml(humanize(data.approval_status))}</span>
          </div>
          ${decision}
          ${actions ? `<div class="button-row">${actions}</div>` : ""}
        </section>
        <section class="card full" id="audit-card">
          <h3>Audit trail</h3>
          <p class="approval-copy">Loading recorded workflow events...</p>
        </section>
      `;
    }

    function renderProgress(item) {
      const total = item.total_step_count || 0;
      const completed = item.completed_step_count || 0;
      const percent = total === 0 ? 0 : Math.round((completed / total) * 100);
      return `
        <div class="saved-item-progress" aria-label="Progress ${completed} of ${total} steps completed">
          <div class="saved-item-meta">
            <span>Progress: ${completed}/${total} steps complete</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width: ${percent}%"></div>
          </div>
        </div>
      `;
    }

    function renderResponse(data, sourceLabel = "live preview") {
      const steps = data.steps.map(
        (step) => `
          <li>
            <strong>${escapeHtml(step.title)}</strong>
            <div class="step-meta">
              <span class="step-chip">Owner: ${escapeHtml(step.owner)}</span>
              <span class="step-chip">Status: ${escapeHtml(step.status)}</span>
            </div>
            <div>${escapeHtml(step.rationale)}</div>
          </li>
        `
      );

      const risks = data.risks.map((risk) => `<li>${escapeHtml(risk)}</li>`);
      const missingInputs = data.missing_inputs.map((item) => `<li>${escapeHtml(item)}</li>`);
      const followUps = data.follow_up_questions.map((question) => `<li>${escapeHtml(question)}</li>`);
      const successChecks = data.success_checks.map((item) => `<li>${escapeHtml(item)}</li>`);
      const createdAt = formatTimestamp(data.created_at);
      const updatedAt = formatTimestamp(data.updated_at);

      resultsRoot.className = "result-grid";
      resultsRoot.innerHTML = `
        <section class="card full">
          <div class="badges">
            <span class="badge">Workflow type: ${escapeHtml(data.workflow_type.replaceAll("_", " "))}</span>
            <span class="badge">Urgency: ${escapeHtml(data.urgency)}</span>
            <span class="badge">Source: ${escapeHtml(sourceLabel)}</span>
            ${data.approval_status ? `<span class="badge">Approval: ${escapeHtml(humanize(data.approval_status))}</span>` : ""}
            ${createdAt ? `<span class="badge">Created: ${escapeHtml(createdAt)}</span>` : ""}
            ${updatedAt ? `<span class="badge">Updated: ${escapeHtml(updatedAt)}</span>` : ""}
          </div>
          <p>${escapeHtml(data.summary)}</p>
        </section>
        <section class="card full">
          <h3>Ordered steps</h3>
          ${renderList(steps, true)}
        </section>
        <section class="card">
          <h3>Risks</h3>
          ${renderList(risks)}
        </section>
        <section class="card">
          <h3>Missing inputs</h3>
          ${renderList(missingInputs)}
        </section>
        <section class="card">
          <h3>Follow-up questions</h3>
          ${renderList(followUps)}
        </section>
        <section class="card">
          <h3>Success checks</h3>
          ${renderList(successChecks)}
        </section>
        ${renderApprovalControls(data)}
      `;

      resultsRoot.querySelectorAll("[data-approval-action]").forEach((button) => {
        button.addEventListener("click", () => performApprovalAction(button.dataset.approvalAction));
      });

      if (data.workflow_id) {
        loadAuditEvents(data.workflow_id).catch((error) => {
          const auditCard = document.getElementById("audit-card");
          if (auditCard) {
            auditCard.innerHTML = `
              <h3>Audit trail</h3>
              <p class="hint">${escapeHtml(error.message)}</p>
            `;
          }
        });
      }
    }

    function renderSavedPlans(items) {
      if (!items || items.length === 0) {
        savedPlansRoot.className = "saved-empty";
        savedPlansRoot.innerHTML = `
          <div class="empty-state">
            No saved plans yet. Use the save button to create one from the current request.
          </div>
        `;
        return;
      }

      savedPlansRoot.className = "saved-list";
      savedPlansRoot.innerHTML = items
        .slice(0, 6)
        .map((item) => {
          const createdAt = formatTimestamp(item.created_at);
          const updatedAt = formatTimestamp(item.updated_at);
          return `
            <button type="button" class="saved-item ${item.workflow_id === activeSavedWorkflowId ? "active" : ""}" data-workflow-id="${escapeHtml(item.workflow_id)}">
              <div class="saved-item-title">${escapeHtml(item.summary)}</div>
              <div class="saved-item-meta">
                <span>${escapeHtml(item.workflow_type.replaceAll("_", " "))}</span>
                <span>${escapeHtml(item.urgency)}</span>
                <span>approval: ${escapeHtml(humanize(item.approval_status))}</span>
                <span>${escapeHtml(item.workflow_id)}</span>
              </div>
              ${renderProgress(item)}
              <div class="saved-item-meta">
                ${createdAt ? `<span>Created ${escapeHtml(createdAt)}</span>` : ""}
                ${updatedAt ? `<span>Updated ${escapeHtml(updatedAt)}</span>` : ""}
              </div>
            </button>
          `;
        })
        .join("");

      savedPlansRoot.querySelectorAll("[data-workflow-id]").forEach((button) => {
        button.addEventListener("click", () => loadSavedPlan(button.dataset.workflowId));
      });
    }

    async function loadAuditEvents(workflowId) {
      const auditCard = document.getElementById("audit-card");
      if (!auditCard) {
        return;
      }

      const response = await fetch(`/workflow/plans/${workflowId}/audit-events`);
      const events = await response.json();
      if (!response.ok) {
        const detail = typeof events.detail === "string" ? events.detail : "Unable to load the audit trail.";
        throw new Error(detail);
      }

      const rows = events.map((event) => {
        const details = Object.entries(event.details || {})
          .map(([key, value]) => `${humanize(key)}: ${value}`)
          .join(" · ");
        return `
          <li>
            <strong>${escapeHtml(humanize(event.event_type))}</strong>
            <span class="audit-meta">${escapeHtml(event.actor)} · ${escapeHtml(formatTimestamp(event.created_at) || event.created_at)}</span>
            ${details ? `<span class="audit-meta">${escapeHtml(details)}</span>` : ""}
          </li>
        `;
      });

      auditCard.innerHTML = `
        <h3>Audit trail</h3>
        ${rows.length ? `<ul class="audit-list">${rows.join("")}</ul>` : '<p class="approval-copy">No events recorded.</p>'}
      `;
    }

    async function performApprovalAction(action) {
      if (!activeSavedWorkflowId) {
        statusText.textContent = "Save or open a plan before using the approval workflow.";
        statusText.className = "status error";
        return;
      }

      const actor = document.getElementById("actor-name").value.trim();
      if (actor.length < 2) {
        statusText.textContent = "Enter an acting user so the approval event can be attributed.";
        statusText.className = "status error";
        return;
      }

      let endpoint = `/workflow/plans/${activeSavedWorkflowId}/approval-requests`;
      let payload = { actor };
      if (action !== "submit") {
        const note = document.getElementById("decision-note")?.value.trim() || "";
        if (action === "rejected" && !note.trim()) {
          statusText.textContent = "A rejection reason is required.";
          statusText.className = "status error";
          return;
        }
        endpoint = `/workflow/plans/${activeSavedWorkflowId}/approval-decisions`;
        payload = { actor, decision: action, note: note.trim() || null };
      }

      statusText.textContent = action === "submit" ? "Submitting plan for approval..." : `Recording ${action} decision...`;
      statusText.className = "status";

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Unable to update approval state.";
        statusText.textContent = detail;
        statusText.className = "status error";
        return;
      }

      renderResponse(data, `saved plan ${data.workflow_id}`);
      await loadSavedPlans();
      statusText.textContent = `Approval status is now ${humanize(data.approval_status)}.`;
    }

    async function loadSavedPlans() {
      const response = await fetch("/workflow/plans");
      const data = await response.json();
      if (!response.ok) {
        throw new Error("Unable to load saved plans.");
      }
      renderSavedPlans(data);
    }

    async function loadSavedPlan(workflowId) {
      statusText.textContent = "Loading saved plan...";
      statusText.className = "status";

      const response = await fetch(`/workflow/plans/${workflowId}`);
      const data = await response.json();
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Unable to load saved workflow plan.";
        throw new Error(detail);
      }

      activeSavedWorkflowId = data.workflow_id;
      renderResponse(data, `saved plan ${data.workflow_id}`);
      await loadSavedPlans();
      statusText.textContent = `Loaded saved plan ${data.workflow_id}.`;
    }

    async function submitPlan(savePlan = false) {
      const payload = buildPayload();
      statusText.textContent = savePlan ? "Saving workflow plan..." : "Generating plan preview...";
      statusText.className = "status";
      submitButton.disabled = true;
      saveButton.disabled = true;

      try {
        const endpoint = savePlan ? "/workflow/plans" : "/workflow/plan";
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
          const detail = typeof data.detail === "string" ? data.detail : "Unable to generate workflow plan.";
          throw new Error(detail);
        }

        if (savePlan) {
          activeSavedWorkflowId = data.workflow_id;
          renderResponse(data, `saved plan ${data.workflow_id}`);
          await loadSavedPlans();
          statusText.textContent = `Plan saved as ${data.workflow_id}.`;
        } else {
          activeSavedWorkflowId = null;
          renderResponse(data, "live preview");
          await loadSavedPlans();
          statusText.textContent = "Plan generated from the live API response.";
        }
      } catch (error) {
        resultsRoot.className = "placeholder";
        resultsRoot.innerHTML = `
          <div class="empty-state">
            <strong>Unable to render a plan.</strong>
            <p class="hint">Check the request text and try again. The API returns validation errors directly.</p>
          </div>
        `;
        statusText.textContent = error.message;
        statusText.className = "status error";
      } finally {
        submitButton.disabled = false;
        saveButton.disabled = false;
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitPlan(false);
    });

    saveButton.addEventListener("click", async () => {
      await submitPlan(true);
    });

    loadSavedPlans().catch((error) => {
      savedPlansRoot.className = "saved-empty";
      savedPlansRoot.innerHTML = `
        <div class="empty-state">
          <strong>Unable to load saved plans.</strong>
          <p class="hint">${escapeHtml(error.message)}</p>
        </div>
      `;
    });
  </script>
</body>
</html>
        """
    )
