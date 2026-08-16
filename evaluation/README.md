# Workflow evidence evaluation data

`datasets/workflow_evidence_v1.jsonl` is the first versioned, synthetic benchmark
for evidence-backed workflow planning. It contains no employer, customer, or
confidential data.

`datasets/workflow_evidence_challenge_v1.jsonl` adds six paraphrase,
multiple-distractor, conflict, and absence cases. Together they form the
12-case `workflow_evidence_combined_v1` comparison suite.

`datasets/workflow_evidence_context_policy_v1.jsonl` is a separate six-case
adversarial suite for coverage-completing answer context. It includes valid
support coverage, generic coverage false friends, redundant support, and
compound-intent absence cases.

Each JSONL record defines:

- a stable case ID and expected workflow type
- the ambiguous operational request
- synthetic source documents with stable source IDs
- the evidence a correct response should cite
- answer type and difficulty
- expected behavior when evidence is complete, missing, or conflicting

Validate the dataset before using it in an evaluation run:

```bash
python scripts/validate_evaluation_dataset.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_grounding.py
python scripts/validate_evaluation_dataset.py evaluation/datasets/workflow_evidence_challenge_v1.jsonl
python scripts/compare_retrieval_strategies.py
python scripts/evaluate_grounding.py \
  --dataset evaluation/datasets/workflow_evidence_challenge_v1.jsonl \
  --strategy hybrid \
  --output evaluation/results/grounded_answer_challenge_hybrid_v1.json
python scripts/evaluate_grounding.py \
  --additional-dataset evaluation/datasets/workflow_evidence_challenge_v1.jsonl \
  --strategy hybrid \
  --output evaluation/results/grounded_answer_combined_hybrid_v1.json
python scripts/validate_evaluation_dataset.py evaluation/datasets/workflow_evidence_context_policy_v1.jsonl
python scripts/evaluate_grounding.py \
  --dataset evaluation/datasets/workflow_evidence_context_policy_v1.jsonl \
  --strategy hybrid \
  --output evaluation/results/grounded_answer_context_policy_hybrid_v1.json
python scripts/compare_persisted_hybrid.py
```

The evaluator derives deterministic 120-word chunks with 30-word overlap, runs
the BM25-style lexical retriever and reranker at `top_k=3`, and records source
Recall@K, mean reciprocal rank, evidence-absence accuracy, and local retrieval
latency. Its checked-in output is
`results/retrieval_baseline_v1.json`.

The V1 result is 1.00 Recall@3, 1.00 MRR, 1.00 evidence-absence accuracy,
0.0183 ms P50, and 0.0326 ms P95. This is a six-case synthetic engineering
baseline—five cases with expected evidence and one absence case—measured over
300 local searches on the environment recorded in the JSON. It establishes a
reproducible regression contract, not a production retrieval, citation
correctness, groundedness, unsupported-claim, or model-quality claim.

Use `--dataset`, `--output`, `--top-k`, or `--runs-per-case` to create a separate
run without replacing the checked-in baseline, for example:

```bash
python scripts/evaluate_retrieval.py --output /tmp/retrieval-results.json
python scripts/evaluate_grounding.py --output /tmp/grounding-results.json
python scripts/compare_retrieval_strategies.py --output /tmp/retrieval-comparison.json
```

## Retrieval strategy comparison

The dependency-free hybrid combines normalized BM25/reranker score (15%),
cosine similarity over an inspectable sparse operations concept vector (80%),
and filename similarity (5%). It is a deterministic synonym/concept baseline,
not a dense embedding model.

`results/retrieval_strategy_comparison_v1.json` reports:

| Slice | Lexical Recall@3 | Hybrid Recall@3 | Lexical MRR | Hybrid MRR |
| --- | ---: | ---: | ---: | ---: |
| Core | 1.00 | 1.00 | 1.00 | 1.00 |
| Challenge | 0.10 | 1.00 | 0.0667 | 1.00 |
| Combined | 0.55 | 1.00 | 0.5333 | 1.00 |

The recorded combined P95 latency is 0.0627 ms for lexical and 0.1395 ms for
hybrid retrieval over 600 searches per strategy. A transparent compound-intent
gate requires concepts such as `owner + rollback` or `approval + rollback` in
the same passage for accountability and authorization questions. Candidates
then receive `strong`, `supporting`, or `weak` relevance labels based on matched
core operations concepts and are reranked deterministically. Hybrid
absence accuracy is now 1.00 on both challenge and combined slices; lexical
remains 0.00 on the challenge slice and 0.50 combined. The gate is a narrow
deterministic policy, not a calibrated probability or general semantic claim.

## Challenge grounded-answer baseline

`results/grounded_answer_challenge_hybrid_v1.json` records 1.00 grounding-
behavior accuracy, citation correctness, citation coverage, expected-source
precision, and expected-source recall, with a 0.00 unsupported-claim rate
across 11 extractive claims. Recorded P95 answer latency is 0.2497 ms over 300
runs. When strong evidence exists, the answerer excludes lower tiers unless a
supporting passage contributes both a query core concept not covered by the
strong set and a new non-core query anchor. It reports both the context policy
and excluded-result count.

`results/grounded_answer_combined_hybrid_v1.json` extends the same evaluation
to all 12 cases and 24 extractive claims. It records 1.00 expected-source
precision, 1.00 expected-source recall, and 0.2154 ms P95 latency over 600 runs.
The core release case now admits a support-coverage passage because it adds the
otherwise uncovered `readiness` concept. Challenge distractors remain excluded
because they do not provide the required uncovered-core plus new-anchor
combination. This is a deterministic result on a small synthetic suite with a
hand-authored concept map, not general semantic relevance.

## Context-policy adversarial baseline

`results/grounded_answer_context_policy_hybrid_v1.json` evaluates six cases
and nine extractive claims. It records 1.00 grounding-behavior accuracy,
citation correctness, citation coverage, expected-source precision, and
expected-source recall, with a 0.00 unsupported-claim rate and 0.1866 ms P95
latency over 300 runs.

The V3 hybrid maps only the explicit phrase `support coverage` to readiness;
generic unit-test and market coverage remain weak. Complementary support must
add an uncovered core concept and a new non-core query anchor. When no strong
passage exists, supporting-only context excludes weak results. These rules are
inspectable regression policies over synthetic cases, not general relevance
calibration.

## Persisted hybrid comparison

`results/persisted_hybrid_comparison_v1.json` compares the V3 sparse hybrid
with a standard-library SQLite chunk index across all 18 synthetic cases and
49 chunks. Both strategies record 1.00 Recall@3, MRR, and evidence-absence
accuracy.

Over 900 fully warm searches per strategy, sparse P50/P95 latency is
0.0921/0.1550 ms and persisted P50/P95 is 0.0820/0.1310 ms. The persisted index
uses 49,152 bytes. Its 18 cold corpus builds take 10.4830 ms total with 0.7443 ms
P95; loading all corpora from SQLite after restart takes 2.0261 ms total with
0.1504 ms P95. The run records 18 restart disk hits and 900 warm memory hits.

Corpus fingerprints cover source content, provenance fields, chunk size, and
overlap configuration, so changed evidence creates a new index entry. The API
uses the same retriever with workflow namespaces, upload-time refresh, and
logical stale-corpus cleanup. This benchmark still does not measure concurrent
writes, physical SQLite compaction, large documents, or a remote database.

## Grounded-answer baseline

The deterministic answerer extracts up to five cited claims from the top three
retrieved chunks. It labels responses as grounded at 40% or greater normalized
query-term coverage, partial below that threshold, and insufficient when no
supporting passage is retrieved. `results/grounded_answer_baseline_v1.json`
records 1.00 grounding-behavior accuracy, 1.00 citation correctness, 1.00
citation coverage, 1.00 expected-source precision, and a 0.00 unsupported-claim
rate across 13 claims. Its recorded local P50/P95 answer latency is
0.0659/0.1050 ms over 300 runs.

Citation correctness here is a strict mechanical check: normalized claim text
must occur in the cited source. Because the answerer is extractive, the result
does not measure semantic entailment of paraphrases or generated prose. The
six-case synthetic set is too small to support production, user-quality, or
generalized groundedness claims; it is a repeatable regression fixture.
