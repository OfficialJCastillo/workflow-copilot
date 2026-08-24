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
- Structured request logs, validated request IDs, and rolling latency/error metrics
- API request volume and P95 latency shown in the browser workspace
- Bounded UTF-8 text and PDF ingestion with persisted extracted evidence
- Stable source citations, SHA-256 fingerprints, duplicate detection, and evidence audit events
- Versioned synthetic evaluation dataset covering grounded, missing, and conflicting evidence
- Deterministic overlapping evidence chunks with BM25-style lexical retrieval and transparent reranking
- Interactive ranked evidence search with citations, matched terms, scores, and explicit no-evidence behavior
- Reproducible six-case synthetic baseline: 1.00 Recall@3, 1.00 MRR, 1.00 evidence-absence accuracy, and 0.0326 ms local P95 retrieval latency
- Deterministic extractive answers with claim-level citations, partial-evidence warnings, and abstention
- Grounded-answer synthetic baseline across 13 claims: 1.00 citation correctness, 0.00 unsupported-claim rate, and 0.1050 ms local P95 answer latency
- Selectable lexical and dependency-free sparse concept-vector hybrid retrieval in the API and browser
- Transparent compound-intent abstention diagnostics for accountability, authorization, and explicit conflict queries
- Inspectable strong/supporting/weak relevance labels with deterministic tiered candidate reranking
- Supporting-evidence admission only when it completes an uncovered query core concept and adds a new non-core anchor
- Twelve-case comparison: hybrid Recall@3, MRR, and evidence-absence accuracy 1.00; lexical Recall@3 0.55 and combined absence accuracy 0.50
- Hybrid challenge and combined grounded-answer precision and recall 1.00
- Six-case context-policy adversarial suite: precision and recall 1.00 across nine cited claims
- Eighteen-case SQLite-persisted hybrid comparison: quality parity, 0.1310 ms warm P95, and a 48 KiB index
- Runtime hybrid index refresh on evidence upload, fingerprint cleanup, restart reuse, and API cache diagnostics
- Explicit actor-attributed evidence deletion, last-source namespace cleanup, and optional SQLite compaction diagnostics
- Eight-worker lifecycle benchmark over 384 documents and 1,920 chunks with zero recorded lock errors and complete cleanup invariants
- Optional 30-case sparse/dense comparison with development/test splits, explicit pending-human-review labels, and a failed production-promotion gate
- Evaluation-only gated fusion improves the inspected 30-case suite to 0.98 Recall@3, 0.98 MRR, and 1.00 absence accuracy while explicitly failing human-review and blind-test gates

## Next implementation milestone

- Human review for the 12 candidate-labelled dense comparison cases
- Validation of gated sparse/dense fusion on an untouched human-reviewed set
- Expand adversarial retrieval cases beyond the hand-authored concept map
- Grounded-answer evaluation over the challenge suite with human usefulness labels
- Optional model-backed answerer evaluated against the same citation contract
- Durable metrics export and deployment monitoring
- One deployed environment using synthetic data

The current figures are engineering regression baselines over 12 synthetic
cases, not production-quality or user-quality claims. The hybrid gate resolves
the targeted compound-intent absence case, and tiered reranking removes the
challenge distractors. Coverage-completing context selection restores the
secondary support source while retaining 1.00 combined expected-source
precision and recall. A separate six-case suite rejects generic coverage false
friends while preserving valid completion, also at 1.00 precision and recall.
The persisted index preserves retrieval quality and improves warm P95 from
0.1550 ms to 0.1310 ms on 18 tiny cases. The API now refreshes the active
workflow fingerprint after evidence uploads, reuses it across restarts, removes
stale unreferenced corpora, and exposes index counters. Evidence deletion now
refreshes or clears that workflow namespace, retains an attributed audit event,
and can reclaim free SQLite pages when delete-time compaction is enabled.
The larger lifecycle fixture now verifies concurrent build, refresh,
partial-delete refresh, restart load, last-source cleanup, and exclusive
compaction over 384 synthetic documents. The first optional dense run improves
held-out paraphrase recall but regresses absence handling and expanded-suite
recall, so the API retains sparse hybrid retrieval. Human review and a fusion
evaluation remain. A follow-up gated fusion run improves the inspected suite's
quality metrics, but it is not promotion evidence because its labels are still
synthetic candidates and its evaluation cases were visible during gate design.

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
