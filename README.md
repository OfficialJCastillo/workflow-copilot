# workflow-copilot

A lightweight workflow planning API for turning messy operational requests into structured steps, owners, risks, and follow-up actions.

## Overview

`workflow-copilot` is a narrow, product-facing v1 for teams that need clearer execution plans before they automate anything. Instead of directly calling external tools, this version focuses on workflow decomposition:

- accept a natural-language task request
- infer a workflow category
- generate ordered action steps
- identify missing inputs and execution risks
- suggest checkpoints and success criteria
- expose the result through a small FastAPI service

This repository is intentionally scoped to deterministic local logic so it stays easy to review, test, and publish.

## V1 Scope

- Local FastAPI service
- Deterministic workflow planning with no hosted dependencies
- SQLite-backed workflow persistence for saved plans and step updates
- Workflow categories for onboarding, incident response, release prep, vendor approval, and recurring operations
- Structured response schema with steps, blockers, risks, and follow-up questions
- Simple urgency and risk heuristics
- Smoke tests for the API-facing pipeline

## Architecture

```text
workflow-copilot/
├── app/
│   ├── api/
│   ├── schemas/
│   └── services/
├── tests/
├── README.md
├── requirements.txt
└── main.py
```

## Example Workflow

1. Send a task request such as "Prepare a minor release for a customer-facing API next Thursday."
2. The service classifies the request into a workflow type.
3. It returns an ordered plan with owners, dependencies, risks, and success checks.
4. A caller can render the plan in a UI, ticketing flow, or internal tool.

## How To Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## API Endpoints

- `GET /health`
- `POST /workflow/plan`
- `POST /workflow/plans`
- `GET /workflow/plans`
- `GET /workflow/plans/{workflow_id}`
- `PATCH /workflow/plans/{workflow_id}/steps/{step_id}`

## Example Response

```json
{
  "workflow_id": "wf-3f6fd803523a",
  "workflow_type": "release_preparation",
  "summary": "Plan a controlled release with approvals, validation, and rollback readiness.",
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

## Design Notes

- The service is intentionally deterministic so the output is inspectable and stable.
- The workflow categories are implemented as lightweight templates plus request-specific heuristics.
- SQLite persistence makes the scaffold usable for saved workflows, step tracking, and simple product demos even before adding an LLM-backed planning layer.

## Roadmap

- add calendar-aware due date handling
- add user and team assignment rules
- add Slack/Jira adapter examples
- add optional model-backed rewrite and follow-up generation
