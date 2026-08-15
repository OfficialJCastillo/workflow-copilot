# workflow-copilot

[![CI](https://github.com/OfficialJCastillo/workflow-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/OfficialJCastillo/workflow-copilot/actions/workflows/ci.yml)

A workflow planning and approval service that turns messy operational requests into structured, reviewable execution plans with an audit trail.

## Overview

`workflow-copilot` is the foundation for an enterprise operations copilot: a reviewer can turn an ambiguous request into a structured plan, save it, submit it for human approval, and inspect every lifecycle event. The current release focuses on explainable workflow decomposition and controlled execution:

- accept a natural-language task request
- infer a workflow category
- generate ordered action steps
- identify missing inputs and execution risks
- suggest checkpoints and success criteria
- move saved plans through draft, pending approval, approved, and rejected states
- attribute approval decisions and retain an immutable workflow audit trail
- expose the full flow through FastAPI and a React case-management interface

The planning logic stays deterministic so behavior is easy to review and test, while the runtime now mirrors a deployable full-stack service.

## Demo Snapshot

Full-stack approval workspace preview:

![workflow-copilot demo snapshot](docs/workflow-demo-snapshot.svg)

## V1 Scope

- Container-ready FastAPI service
- Deterministic workflow planning with no hosted dependencies
- PostgreSQL persistence in the full-stack environment, with SQLite retained for lightweight local development
- SQLAlchemy Core storage adapter and Alembic schema migrations
- Workflow categories for onboarding, incident response, release prep, vendor approval, and recurring operations
- Structured response schema with steps, blockers, risks, and follow-up questions
- Request-aware urgency, summary, risk, and missing-input heuristics for edge cases like vague asks and conflicting timelines
- React and TypeScript case-management interface for intake, execution tracking, approvals, and audit review
- Tiny embedded demo UI at `GET /` for a zero-install API preview
- Saved-plan list metadata with progress counts plus created and updated timestamps
- Human approval state machine with required rejection reasons
- Actor-attributed audit events for creation, step changes, submissions, and decisions
- Docker Compose environment for the web application, API, and PostgreSQL
- Backend, frontend, migration, and PostgreSQL integration tests

## Architecture

```text
React + TypeScript interface
             |
             v
       FastAPI routes <---- embedded demo / API clients
             |
             +--> deterministic planning engine
             |
             +--> approval state machine
             |
             v
   SQLAlchemy persistence layer
             |
             +--> PostgreSQL (Compose / deployment)
             +--> SQLite (lightweight local tests)
             |
             +--> Alembic migrations
```

The [flagship product brief](docs/flagship-product-brief.md) defines the target user, end-to-end scenario, non-goals, and completion gates for the next full-stack milestone.

## Example Workflow

1. Send a task request such as "Prepare a minor release for a customer-facing API next Thursday."
2. Open the browser demo or call the API directly.
3. The service classifies the request into a workflow type.
4. It returns an ordered plan with owners, dependencies, risks, and success checks.
5. Save the plan to the configured database and reopen it from the case queue.
6. Submit the saved plan for approval.
7. Approve or reject it with an attributed decision note.
8. Inspect the audit trail before handing approved work to a downstream system.

## Quick Start With Docker

Docker Compose is the recommended path because it starts PostgreSQL, applies
all migrations, launches the API, and serves the production frontend together:

```bash
cp .env.example .env
docker compose up --build
```

Open `http://127.0.0.1:5173/`. The API and interactive documentation are
available at `http://127.0.0.1:8000/` and
`http://127.0.0.1:8000/docs`, respectively.

Stop the services without deleting the PostgreSQL volume:

```bash
docker compose down
```

## Local Development With SQLite

SQLite remains the zero-service development default:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

In a second terminal, start the case-management frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Open the React application:

```text
http://127.0.0.1:5173/
```

The lightweight embedded demo remains available directly from FastAPI:

```text
http://127.0.0.1:8000/
```

## API Endpoints

- `GET /` (tiny demo UI)
- `GET /health`
- `GET /ready` (database readiness and backend type)
- `POST /workflow/plan`
- `POST /workflow/plans`
- `GET /workflow/plans`
- `GET /workflow/plans/{workflow_id}`
- `PATCH /workflow/plans/{workflow_id}/steps/{step_id}`
- `POST /workflow/plans/{workflow_id}/approval-requests`
- `POST /workflow/plans/{workflow_id}/approval-decisions`
- `GET /workflow/plans/{workflow_id}/audit-events`

## Case-management interface

The React interface provides a responsive operations workspace to:

- enter an operational request
- set requester role and team name
- generate and save a structured case through `POST /workflow/plans`
- reopen recent saved plans from the configured database
- see saved-plan progress, created timestamps, and updated timestamps in the history list
- inspect steps, risks, missing inputs, follow-up questions, and success checks without using a separate API client
- submit plans for approval and record approve/reject decisions
- inspect actor-attributed audit events directly in the plan view

For deployments where the frontend and API use different origins, set
`VITE_API_BASE_URL` for the frontend and provide a comma-separated
`WORKFLOW_CORS_ORIGINS` value to the API. Local Vite origins are allowed by
default.

## Database Configuration And Migrations

The API reads `WORKFLOW_DATABASE_URL`. When unset, it uses
`sqlite+pysqlite:///data/workflow_copilot.db`. Compose configures a Psycopg 3
PostgreSQL URL automatically.

Apply migrations before starting a manually configured environment:

```bash
WORKFLOW_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/workflow_copilot" \
  alembic upgrade head
```

`WORKFLOW_AUTO_CREATE_SCHEMA=0` disables the convenience schema creation used
by lightweight local development. The Compose API sets this flag because its
startup command always applies Alembic migrations first.

## Example Saved Plan Response

```json
{
  "workflow_id": "wf-3f6fd803523a",
  "workflow_type": "release_preparation",
  "summary": "Plan a controlled release with approvals, validation, and rollback readiness.",
  "approval_status": "draft",
  "steps": [
    {
      "step_id": "step-1",
      "title": "Confirm release scope and deadline",
      "owner": "requester",
      "status": "pending"
    }
  ],
  "risks": [
    "Customer-facing changes increase rollback sensitivity."
  ],
  "missing_inputs": [
    "Exact release date and deployment window."
  ]
}
```

The saved-plan list endpoint also returns compact progress metadata such as `completed_step_count`, `total_step_count`, and `step_status_counts` so the demo can show history state without fetching every full plan first.

## Design Notes

- The service is intentionally deterministic so the output is inspectable and stable.
- The workflow categories are implemented as lightweight templates plus request-specific heuristics.
- SQLAlchemy Core keeps workflow and audit transactions consistent across SQLite and PostgreSQL.
- Alembic upgrades both clean databases and the repository's earlier SQLite schema.
- Approval transitions are explicit: draft or rejected plans may be submitted, and only pending plans may be approved or rejected.
- Approval changes and step updates write audit events in the same database transaction as the state change.
- The React workspace persists plans, drives step and approval decisions, and renders audit history without requiring a separate API client.
- Frontend lint, component tests, production builds, PostgreSQL integration tests, migrations, and container builds run in GitHub Actions.

## GitHub Setup Notes

Suggested repo description:

`Structured workflow planning API for turning messy operational requests into ordered steps, risks, and follow-up actions.`

Suggested topics:

- `workflow`
- `planning`
- `fastapi`
- `python`
- `sqlite`
- `postgresql`
- `alembic`
- `docker`
- `react`
- `typescript`
- `operations`
- `productivity`

## Roadmap

- add calendar-aware due date handling
- add user and team assignment rules
- add document upload and text/PDF ingestion
- add an evidence panel with source citations
- add structured logging, request IDs, and latency measurements
- add Slack/Jira adapter examples
- add optional model-backed rewrite and follow-up generation

## License

This project is available under the [MIT License](LICENSE).
