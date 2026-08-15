# Enterprise Operations Copilot — Product Brief

## Product outcome

Help an operations lead turn an ambiguous request into an evidence-backed execution plan, route it through human approval, and retain an inspectable record of what happened and why.

The portfolio goal is to demonstrate the complete forward-deployed engineering motion: clarify a business problem, integrate its data, build a usable workflow, measure reliability, deploy it, and improve it from user feedback.

## Primary user

An operations or engineering lead responsible for coordinating work across teams. They receive incomplete requests, need to identify missing information and risk, and cannot trigger downstream actions without an accountable reviewer.

## Golden workflow

1. The user creates an operational request.
2. The system identifies the workflow type, urgency, missing inputs, and risks.
3. The user reviews and edits a structured execution plan.
4. Supporting documents and source evidence are attached to the case.
5. The plan is submitted for approval.
6. A reviewer approves or rejects it with an attributed note.
7. An approved plan is handed to a downstream adapter in preview mode.
8. Every state change appears in the audit history.
9. The user records whether the plan was useful and what needed correction.

## Initial enterprise scenario

A platform team is preparing a customer-facing API release. The original request contains an ambiguous deadline and incomplete approval details. The copilot must surface the conflict, propose a release workflow, identify missing rollback information, show the evidence used, and require approval before a handoff can be generated.

## Current foundation

- Deterministic workflow classification and plan generation
- Typed FastAPI contracts
- SQLAlchemy persistence with SQLite and PostgreSQL support
- Alembic schema migrations, including legacy SQLite upgrades
- Human approval state machine
- Actor-attributed audit trail
- React and TypeScript case-management interface
- Browser-based approval and audit demonstration flow
- Backend and frontend tests in GitHub Actions
- PostgreSQL integration coverage and container build validation
- Docker Compose environment for the frontend, API, and database

## Next implementation milestone

- Document upload and text/PDF ingestion
- Evidence panel with citations
- Versioned evaluation dataset
- Structured logging, request IDs, and latency measurements
- One deployed environment using synthetic data

## Non-goals for the next milestone

- Autonomous execution without approval
- Multiple model-serving backends
- Production integrations with confidential systems
- A general-purpose chatbot
- A large collection of unrelated workflow templates

## Completion gates

- A clean checkout starts through one documented Docker Compose path.
- A reviewer can complete the golden workflow in the browser.
- Backend, frontend, integration, and end-to-end tests run in CI.
- The demo reports retrieval quality, unsupported-claim rate, P50/P95 latency, and cost per request.
- At least three external users complete the workflow and produce documented product changes.
- The README includes a live URL, architecture diagram, measured results, tradeoffs, and failure cases.
