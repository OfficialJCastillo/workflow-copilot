from typing import Literal
from typing import Self

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


ApprovalStatus = Literal["draft", "pending_approval", "approved", "rejected"]
RetrievalStrategy = Literal["lexical", "hybrid"]


class WorkflowPlanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_text: str = Field(min_length=8, max_length=10_000)
    requester_role: str = Field(default="requester", min_length=2, max_length=120)
    team_name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def normalize_optional_team_name(self) -> Self:
        if self.team_name == "":
            self.team_name = None
        return self


class WorkflowStep(BaseModel):
    step_id: str
    title: str
    owner: str
    status: str = "pending"
    rationale: str


class WorkflowPlanBase(BaseModel):
    workflow_type: str
    summary: str
    urgency: str
    steps: list[WorkflowStep]
    risks: list[str]
    missing_inputs: list[str]
    follow_up_questions: list[str]
    success_checks: list[str]


class WorkflowPlanResponse(WorkflowPlanBase):
    pass


class StoredWorkflowPlan(WorkflowPlanBase):
    workflow_id: str
    request_text: str
    requester_role: str
    team_name: str | None = None
    created_at: str
    updated_at: str
    approval_status: ApprovalStatus
    decision_by: str | None = None
    decision_note: str | None = None
    decided_at: str | None = None


class WorkflowPlanListItem(BaseModel):
    workflow_id: str
    workflow_type: str
    summary: str
    urgency: str
    request_text: str
    step_status_counts: dict[str, int]
    completed_step_count: int
    total_step_count: int
    approval_status: ApprovalStatus
    created_at: str
    updated_at: str


class WorkflowStepStatusUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: str = Field(pattern="^(pending|in_progress|completed|blocked)$")
    actor: str = Field(default="workflow_api", min_length=2, max_length=120)


class ApprovalSubmissionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    actor: str = Field(min_length=2, max_length=120)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    actor: str = Field(min_length=2, max_length=120)
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_rejection_note(self) -> Self:
        if self.note == "":
            self.note = None
        if self.decision == "rejected" and not (self.note and self.note.strip()):
            raise ValueError("A rejection note is required.")
        return self


class WorkflowAuditEvent(BaseModel):
    event_id: str
    workflow_id: str
    event_type: str
    actor: str
    details: dict[str, str]
    created_at: str


class WorkflowEvidence(BaseModel):
    evidence_id: str
    citation_id: str
    workflow_id: str
    filename: str
    media_type: str
    excerpt: str
    source_sha256: str
    page_count: int | None = None
    character_count: int
    created_at: str


class EvidenceDeletionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    actor: str = Field(min_length=2, max_length=120)


class EvidenceSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)
    strategy: RetrievalStrategy = "lexical"


class EvidenceSearchResult(BaseModel):
    chunk_id: str
    evidence_id: str
    citation_id: str
    filename: str
    chunk_index: int
    content: str
    retrieval_score: float
    rerank_score: float
    matched_terms: list[str]
    relevance_label: str
    core_matches: list[str]


class EvidenceSearchResponse(BaseModel):
    query: str
    strategy: RetrievalStrategy
    retriever: str
    index_backend: Literal["sqlite"] | None = None
    source_count: int
    total_chunks: int
    evidence_found: bool
    latency_ms: float
    results: list[EvidenceSearchResult]
    abstention_reason: str | None = None
    required_terms: list[str] = Field(default_factory=list)


class GroundedAnswerRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)
    max_claims: int = Field(default=5, ge=1, le=10)
    strategy: RetrievalStrategy = "lexical"


class GroundedAnswerClaim(BaseModel):
    claim_id: str
    text: str
    evidence_id: str
    citation_id: str
    filename: str
    chunk_id: str
    matched_terms: list[str]


class GroundedAnswerResponse(BaseModel):
    query: str
    strategy: RetrievalStrategy
    retriever: str
    index_backend: Literal["sqlite"] | None = None
    status: Literal["grounded", "partial_evidence", "insufficient_evidence"]
    answer: str
    source_count: int
    total_chunks: int
    query_term_coverage: float
    latency_ms: float
    claims: list[GroundedAnswerClaim]
    abstention_reason: str | None = None
    required_terms: list[str] = Field(default_factory=list)
    context_policy: Literal[
        "all_ranked",
        "strong_only",
        "strong_plus_supporting",
        "supporting_only",
    ] = "all_ranked"
    excluded_result_count: int = 0


class HybridIndexStatusResponse(BaseModel):
    enabled: bool
    backend: Literal["sqlite"] | None = None
    retriever: str
    indexed_corpus_count: int
    indexed_chunk_count: int
    indexed_namespace_count: int
    index_size_bytes: int
    memory_cache_hits: int
    disk_cache_hits: int
    cache_misses: int
    compact_on_delete: bool
    compaction_count: int
    last_compaction_reclaimed_bytes: int


class LatencyMetrics(BaseModel):
    sample_count: int
    p50: float
    p95: float
    maximum: float


class ServiceMetricsResponse(BaseModel):
    service: str
    started_at: str
    uptime_seconds: float
    request_count: int
    server_error_count: int
    server_error_rate: float
    latency_ms: LatencyMetrics
