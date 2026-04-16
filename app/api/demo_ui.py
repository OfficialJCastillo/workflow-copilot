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
      max-width: 1100px;
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
      max-width: 60ch;
      font-size: 1.08rem;
      line-height: 1.5;
      color: var(--muted);
    }

    .layout {
      display: grid;
      gap: 20px;
      grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
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

    .panel-body {
      padding: 24px;
      display: grid;
      gap: 18px;
    }

    .form-copy {
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

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.65; cursor: wait; transform: none; }

    .status {
      margin: 0;
      min-height: 1.25rem;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      color: var(--muted);
    }

    .status.error { color: #9f1239; }

    .result-header {
      padding: 24px 24px 0;
      display: grid;
      gap: 10px;
    }

    .result-header h2 {
      margin: 0;
      font-size: 1.55rem;
    }

    .result-copy {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
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

    .placeholder {
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
        and inspect the returned workflow type, ordered steps, risks, missing inputs, and follow-up questions.
      </p>
    </section>

    <section class="layout">
      <form class="panel" id="plan-form">
        <div class="panel-body">
          <p class="form-copy">
            This demo previews the existing <code>POST /workflow/plan</code> response. It does not save plans or update step state.
          </p>

          <label>
            Task request
            <textarea id="request-text" name="request_text" required>Prepare a minor release for a customer-facing API next Thursday.</textarea>
          </label>

          <label>
            Requester role
            <input id="requester-role" name="requester_role" value="engineering_manager" />
          </label>

          <label>
            Team name
            <input id="team-name" name="team_name" value="Platform" />
          </label>

          <button type="submit" id="submit-button">Generate workflow plan</button>
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
      </section>
    </section>
  </main>

  <script>
    const form = document.getElementById("plan-form");
    const statusText = document.getElementById("status-text");
    const submitButton = document.getElementById("submit-button");
    const resultsRoot = document.getElementById("results-root");

    function renderList(items, ordered = false, className = "") {
      if (!items || items.length === 0) {
        return '<p class="hint">No items returned for this section.</p>';
      }

      const tag = ordered ? "ol" : "ul";
      return `<${tag} class="${className}">${items.join("")}</${tag}>`;
    }

    function renderResponse(data) {
      const steps = data.steps.map(
        (step) => `
          <li>
            <strong>${step.title}</strong>
            <div class="step-meta">
              <span class="step-chip">Owner: ${step.owner}</span>
              <span class="step-chip">Status: ${step.status}</span>
            </div>
            <div>${step.rationale}</div>
          </li>
        `
      );

      const risks = data.risks.map((risk) => `<li>${risk}</li>`);
      const missingInputs = data.missing_inputs.map((item) => `<li>${item}</li>`);
      const followUps = data.follow_up_questions.map((question) => `<li>${question}</li>`);
      const successChecks = data.success_checks.map((item) => `<li>${item}</li>`);

      resultsRoot.className = "result-grid";
      resultsRoot.innerHTML = `
        <section class="card full">
          <div class="badges">
            <span class="badge">Workflow type: ${data.workflow_type.replaceAll("_", " ")}</span>
            <span class="badge">Urgency: ${data.urgency}</span>
          </div>
          <p>${data.summary}</p>
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
      `;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const payload = {
        request_text: document.getElementById("request-text").value,
        requester_role: document.getElementById("requester-role").value || "requester",
        team_name: document.getElementById("team-name").value || null,
      };

      statusText.textContent = "Generating plan preview...";
      statusText.className = "status";
      submitButton.disabled = true;

      try {
        const response = await fetch("/workflow/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
          const detail = typeof data.detail === "string" ? data.detail : "Unable to generate workflow plan.";
          throw new Error(detail);
        }

        renderResponse(data);
        statusText.textContent = "Plan generated from the live API response.";
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
      }
    });
  </script>
</body>
</html>
        """
    )
