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
- Bounded UTF-8 text and PDF evidence uploads with extracted source previews and stable citations
- SHA-256 source fingerprints, duplicate detection, and actor-attributed evidence audit events
- Deterministic overlapping evidence chunks with BM25-style lexical retrieval and transparent reranking signals
- Selectable dependency-free hybrid retrieval combining BM25 with an inspectable operations concept vector
- Transparent compound-intent gating that abstains unless required concepts occur in the same passage
- Inspectable strong/supporting/weak relevance tiers with deterministic candidate reranking
- Coverage-completing supporting evidence admission with a non-core query anchor
- Runtime SQLite hybrid index with corpus fingerprint invalidation, restart reuse, and stale-corpus cleanup
- Actor-confirmed evidence deletion with namespace cleanup and optional SQLite compaction
- Evidence search in the API and React workspace, including ranked citations, matched terms, scores, and explicit no-evidence results
- Deterministic extractive answers with claim-level citations, partial-evidence warnings, and abstention
- Versioned synthetic evaluation data for grounded, missing-evidence, and conflicting-evidence cases
- Tiny embedded demo UI at `GET /` for a zero-install API preview
- Saved-plan list metadata with progress counts plus created and updated timestamps
- Human approval state machine with required rejection reasons
- Actor-attributed audit events for creation, step changes, submissions, and decisions
- Structured JSON request logs with validated correlation IDs and latency measurements
- Process-level request, error-rate, and P50/P95 latency metrics exposed in the API and UI
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
             +--> text/PDF evidence ingestion + citations
             |
             +--> lexical or persisted hybrid chunk ranking
             |
             +--> cited extractive answers + abstention
             |
             +--> request IDs + latency metrics + JSON logs
             |
             v
   SQLAlchemy persistence layer
             |
             +--> PostgreSQL (Compose / deployment)
             +--> SQLite (lightweight local tests)
             |
             +--> plans + audit events + extracted evidence
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
6. Attach a UTF-8 text or PDF source and review its stable citation and extracted preview.
7. Search the attached sources and inspect the ranked, cited supporting passages.
8. Compare lexical and hybrid retrieval, then draft a grounded answer using the selected strategy.
9. Submit the saved plan for approval.
10. Approve or reject it with an attributed decision note.
11. Inspect the audit trail before handing approved work to a downstream system.

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
- `GET /metrics` (request volume, server-error rate, and rolling P50/P95 latency)
- `GET /metrics/retrieval-index` (hybrid-index size, corpus/chunk counts, cache activity, and compaction activity)
- `POST /workflow/plan`
- `POST /workflow/plans`
- `GET /workflow/plans`
- `GET /workflow/plans/{workflow_id}`
- `PATCH /workflow/plans/{workflow_id}/steps/{step_id}`
- `POST /workflow/plans/{workflow_id}/approval-requests`
- `POST /workflow/plans/{workflow_id}/approval-decisions`
- `GET /workflow/plans/{workflow_id}/audit-events`
- `POST /workflow/plans/{workflow_id}/evidence` (multipart UTF-8 text or PDF upload)
- `GET /workflow/plans/{workflow_id}/evidence`
- `DELETE /workflow/plans/{workflow_id}/evidence/{evidence_id}` (JSON body with the deleting actor)
- `POST /workflow/plans/{workflow_id}/evidence/search` (ranked search with `strategy: lexical|hybrid`)
- `POST /workflow/plans/{workflow_id}/evidence/answer` (cited answer using the selected retrieval strategy)

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
- attach or remove text/PDF evidence and review stable source citations, extraction previews, fingerprints, and deletion audits
- switch between lexical BM25 and hybrid concept-vector search and inspect ranked passages
- draft an extractive grounded answer and inspect claim-level source provenance before approval
- monitor API request volume and rolling P95 latency in the portfolio summary

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

`WORKFLOW_HYBRID_INDEX_PATH` selects the derived SQLite hybrid index and
defaults to `data/workflow_hybrid_index.db`. Compose stores `/app/data` in the
`workflow_hybrid_index_data` volume. Evidence remains authoritative in the
workflow database; the index can be rebuilt from it.

`WORKFLOW_HYBRID_INDEX_COMPACT_ON_DELETE=1` runs SQLite `VACUUM` after each
evidence deletion. It defaults to `0` because physical compaction takes an
exclusive index operation and can be expensive on a large corpus. Logical
deletion, namespace cleanup, and orphaned-corpus removal always run; enable
compaction when deleted text must also be reclaimed from free SQLite pages
immediately.

## Observability

Every API response includes a validated `X-Request-ID` correlation header and
a `Server-Timing` value for application latency. Clients may supply an
`X-Request-ID` containing letters, numbers, dots, underscores, or hyphens; the
service replaces invalid values to prevent log injection.

The `workflow_copilot.http` logger writes one JSON record per request with the
method, path, status, duration, request ID, and outcome. Set
`WORKFLOW_LOG_LEVEL` to control its logging threshold.

`GET /metrics` reports request volume, HTTP 5xx rate, uptime, and P50/P95/max
latency over the most recent 1,000 requests. This in-process window is suitable
for a single-instance portfolio deployment and intentionally resets on restart;
a production multi-replica deployment should export the same signals to a
durable metrics backend.

## Evidence Ingestion And Evaluation Data

Evidence uploads are deliberately narrow and inspectable:

- accepted formats are UTF-8 `.txt` and `.pdf`
- raw upload size is limited to 5 MB
- PDFs are limited to 200 pages
- extracted text is limited to 500,000 characters
- encrypted PDFs and documents with no readable text are rejected
- full extracted text is stored for retrieval, while evidence-list responses return a bounded preview
- each source receives a stable `SRC-*` citation and SHA-256 fingerprint
- uploading the same source to the same workflow is idempotent

Search derives deterministic 120-word chunks with a 30-word overlap from the
persisted extracted text. A BM25-style lexical scorer creates the initial
ranking, then an inspectable reranker adds query-term coverage, adjacent-term
coverage, and filename overlap. Results include stable source citations,
matched normalized terms, and both scores. If no query term is supported, the
API returns `evidence_found: false` instead of choosing an unrelated passage.

The optional `hybrid` strategy combines 15% normalized lexical score, 80%
cosine similarity over a sparse operations-domain concept vector, and 5%
filename similarity. The concept map makes limited relationships such as
`backout`/`revert` → `rollback`, `accountable` → `owner`, and `entitlement` →
`access` explicit and reviewable. It adds no package, model download, image
size, or hosted dependency; it is not a dense embedding or general semantic
retriever.

For accountability, authorization, and explicit conflict queries, the hybrid
strategy applies a narrow compound-intent gate after ranking. If concepts such
as `owner + rollback` or `approval + rollback` do not occur in the same
passage, it returns no results with `compound_intent_not_supported` and the
required terms. The API and UI expose that diagnostic. This is a deterministic
rule for a known failure class, not a calibrated confidence probability.

After the compound gate, hybrid candidates receive an inspectable relevance
tier based on core operations concepts. Two or more matching concepts (or a
fully supported compound intent) is `strong`, one is `supporting`, and none is
`weak`. Results are sorted deterministically by tier, core-concept count,
hybrid score, lexical score, and stable source/chunk identifiers. Evidence
search still shows every ranked candidate. Grounded answers start with `strong`
passages, then admit a `supporting` passage only when it contributes a query
core concept and a new non-core query anchor not covered by the strong set. The
current concept map treats the explicit phrase `support coverage` as a
readiness signal; generic test or market coverage is not promoted. If there is
no strong passage, supporting-tier evidence excludes weak candidates. Responses
expose whether context was all-ranked, strong-only, strong-plus-supporting, or
supporting-only and report how many lower-confidence results were excluded.

Lexical search continues to derive chunks at query time. Hybrid search uses a
SQLite index prepared after each new evidence upload and checked before every
hybrid search or answer. SHA-256 fingerprints cover source content, provenance,
chunk size, and overlap configuration. Each workflow namespace points to one
active fingerprint; replacing it deletes an unreferenced stale corpus while
preserving corpora shared by another namespace. Duplicate uploads reuse the
active index without adding another audit event.

Hybrid API responses identify the concrete retriever and `sqlite` index
backend. `GET /metrics/retrieval-index` reports corpus, chunk, namespace, byte,
memory-hit, disk-hit, and build-miss counters without exposing the filesystem
path. Each successful new upload records an `evidence_index_refreshed` audit
event with a shortened fingerprint and cleanup statistics.

Evidence deletion removes the authoritative extracted-text row, retains an
actor-attributed deletion event, and immediately refreshes the workflow's
remaining fingerprint. Deleting the last source clears its namespace and
orphaned corpus instead of creating an empty index. Search results and grounded
answers are cleared in the browser after confirmation. The index metrics also
report whether delete-time compaction is enabled, how many compactions this
process has run, and the bytes reclaimed by the latest one.

Grounded answers are deliberately extractive: each structured claim is copied
from a retrieved passage, bounded to 600 characters, and paired with its source,
citation, and chunk identifiers. The response reports `grounded`,
`partial_evidence`, or `insufficient_evidence`. Query-term coverage below 40%
produces a partial warning, while no supported passage produces an abstention.
The formatted answer contains only those cited claims plus clearly labeled
system guidance; it does not synthesize new factual statements.

The initial synthetic benchmark lives at
`evaluation/datasets/workflow_evidence_v1.jsonl`. Validate its schema and source
references with:

```bash
python scripts/validate_evaluation_dataset.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_grounding.py
python scripts/compare_retrieval_strategies.py
python scripts/evaluate_grounding.py \
  --dataset evaluation/datasets/workflow_evidence_challenge_v1.jsonl \
  --strategy hybrid \
  --output evaluation/results/grounded_answer_challenge_hybrid_v1.json
python scripts/evaluate_grounding.py \
  --additional-dataset evaluation/datasets/workflow_evidence_challenge_v1.jsonl \
  --strategy hybrid \
  --output evaluation/results/grounded_answer_combined_hybrid_v1.json
python scripts/validate_evaluation_dataset.py \
  evaluation/datasets/workflow_evidence_context_policy_v1.jsonl
python scripts/evaluate_grounding.py \
  --dataset evaluation/datasets/workflow_evidence_context_policy_v1.jsonl \
  --strategy hybrid \
  --output evaluation/results/grounded_answer_context_policy_hybrid_v1.json
python scripts/compare_persisted_hybrid.py
```

The checked-in baseline result is
`evaluation/results/retrieval_baseline_v1.json`:

| Evaluation slice | Result |
| --- | ---: |
| Source Recall@3 | 1.00 |
| Mean reciprocal rank | 1.00 |
| Evidence-absence accuracy | 1.00 |
| Local retrieval latency P50 | 0.0183 ms |
| Local retrieval latency P95 | 0.0326 ms |

These are narrow engineering-baseline measurements over six synthetic cases
(five with expected evidence and one absence case), with 300 timed searches on
the recorded local arm64 environment. They verify the deterministic benchmark
and instrumentation; they are not production-quality, user-quality, citation-
correctness, or model-groundedness claims.

The checked-in grounded-answer result is
`evaluation/results/grounded_answer_baseline_v1.json`:

| Evaluation slice | Result |
| --- | ---: |
| Grounding-behavior accuracy | 1.00 |
| Citation correctness | 1.00 |
| Citation coverage | 1.00 |
| Expected-source precision | 1.00 |
| Unsupported-claim rate | 0.00 |
| Local answer latency P50 | 0.0659 ms |
| Local answer latency P95 | 0.1050 ms |

This second baseline evaluates 13 extractive claims and 300 timed answer runs
over the same six synthetic cases. Citation correctness means that normalized
claim text occurs in its cited source; it does not establish semantic entailment
for generated prose, real-document performance, or human usefulness.

The strategy comparison combines the six core cases with six new paraphrase,
distractor, conflict, and absence challenges. Its checked-in result is
`evaluation/results/retrieval_strategy_comparison_v1.json`:

| Slice | Lexical Recall@3 | Hybrid Recall@3 | Lexical MRR | Hybrid MRR |
| --- | ---: | ---: | ---: | ---: |
| Core (6 cases) | 1.00 | 1.00 | 1.00 | 1.00 |
| Challenge (6 cases) | 0.10 | 1.00 | 0.0667 | 1.00 |
| Combined (12 cases) | 0.55 | 1.00 | 0.5333 | 1.00 |

On the recorded 600-run combined measurement, lexical P95 latency was 0.0627
ms and hybrid P95 was 0.1395 ms. Hybrid evidence-absence accuracy is now 1.00
on both challenge and combined slices, while lexical remains 0.00 on the
challenge slice and 0.50 combined. The compound-intent gate handles the
targeted abstention failures, while relevance tiers and deterministic
reranking move the expected source ahead of non-compound distractors.

The hybrid challenge grounded-answer result evaluates 11 extractive claims:

| Grounding slice | Result |
| --- | ---: |
| Grounding-behavior accuracy | 1.00 |
| Citation correctness | 1.00 |
| Citation coverage | 1.00 |
| Unsupported-claim rate | 0.00 |
| Expected-source precision | 1.00 |
| Expected-source recall | 1.00 |
| Local answer latency P95 | 0.2497 ms |

The combined grounded-answer result covers 24 extractive claims across all 12
cases. Expected-source precision and recall are both 1.00, with local P95
answer latency of 0.2154 ms over 600 runs. In the core release case, a support
coverage passage contributes the otherwise uncovered `readiness` concept and
is admitted alongside the strong release/rollback passage. Challenge access,
vendor, and calendar distractors add no uncovered core concept and remain
excluded. These results use a small synthetic suite and a hand-authored concept
map; they are regression evidence, not a claim of general semantic relevance.

The separate six-case context-policy adversarial suite targets the selection
rule directly. It covers valid support completion, unit-test and market
coverage false friends, redundant support, a supporting-only query, and
distributed compound intent. Its checked-in result evaluates nine claims with
1.00 grounding behavior, citation correctness, expected-source precision, and
expected-source recall; unsupported-claim rate is 0.00 and recorded P95 answer
latency is 0.1866 ms over 300 runs.

The persisted-hybrid comparison covers all 18 synthetic cases and 49 derived
chunks. Sparse and persisted hybrid retrieval both score 1.00 Recall@3, MRR,
and evidence-absence accuracy. Over 900 warm searches each, sparse P50/P95 was
0.0921/0.1550 ms and persisted P50/P95 was 0.0820/0.1310 ms. The SQLite index
was 49,152 bytes. Building 18 cold corpora took 10.4830 ms total with 0.7443 ms
P95 per corpus; loading them after a retriever restart took 2.0261 ms total with
0.1504 ms P95. The result measures a tiny synthetic local workload and does not
predict database, concurrency, or large-corpus performance.

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
- Request logs omit headers, query strings, and bodies so operational correlation does not copy user content into telemetry.
- The initial metrics collector is bounded and process-local, favoring a zero-dependency demo over cross-replica aggregation.
- Evidence ingestion stores normalized extracted text rather than original binaries, reducing storage and simplifying later retrieval while sacrificing original-document download.
- Source fingerprints make duplicate uploads idempotent within a workflow; they are provenance identifiers, not proof that a source is trustworthy.
- Lexical chunks are derived at search time; hybrid chunks are fingerprinted in SQLite and refreshed after evidence uploads.
- The first retriever is lexical and deterministic. It is easy to inspect and benchmark, but vocabulary mismatch remains a known failure mode despite a small normalization map.
- The hybrid sparse vector improves recall for the included operations paraphrases without adding dependencies, but its hand-authored concept map does not generalize like a trained embedding model.
- The hybrid compound-intent gate fixes the benchmark's distributed authorization distractor, but it is a narrow deterministic policy rather than general relevance calibration.
- Coverage-completing context selection raises combined expected-source precision and recall to 1.00 by requiring an uncovered query core concept plus a new non-core anchor; a separate adversarial suite also scores 1.00 precision and recall.
- The runtime hybrid index reuses fingerprinted chunks across restarts, records refresh audits, and removes stale unreferenced corpora; its SQLite file remains derived state rather than the source of truth.
- Evidence deletion is immediate and audited; physical free-page reclamation is opt-in because running SQLite `VACUUM` for every deletion trades lower residual disk usage for a blocking index rewrite.
- Grounded answers are extractive rather than generative, making claim support mechanically verifiable while limiting fluency and cross-source synthesis.
- The partial-evidence threshold is a documented heuristic, not a calibrated confidence probability.
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
- measure delete/refresh/compaction behavior under concurrent larger-corpus workloads
- compare the sparse hybrid with a dense embedding on a larger human-labeled set
- expand adversarial retrieval cases beyond the hand-authored concept map
- add human usefulness labels to the challenge grounded-answer evaluation
- compare extractive grounding with an optional model-backed answerer behind the same citation contract
- export latency and error metrics to a durable monitoring backend
- add Slack/Jira adapter examples
- add optional model-backed rewrite and follow-up generation

## License

This project is available under the [MIT License](LICENSE).
