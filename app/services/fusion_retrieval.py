from dataclasses import dataclass
import re

from app.services.dense_retrieval import DenseEvidenceRetriever
from app.services.dense_retrieval import DensePreparation
from app.services.dense_retrieval import DenseTextEncoder
from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import RankedEvidenceChunk
from app.services.retrieval import RetrievalRun
from app.services.retrieval import SearchDocument


AUTHORIZATION_QUERY = re.compile(
    r"\b(approved?|authori[sz](?:e|ed|ation)|sign[\s-]?off)\b",
    re.IGNORECASE,
)
QUESTION_ACTOR = re.compile(r"\b(who|which)\b", re.IGNORECASE)
OUTCOME_QUERY = re.compile(r"\b(outcome|results?)\b", re.IGNORECASE)
OUTCOME_STATUS = re.compile(
    r"\b(passed?|failed?|completed?|cleared?|approved?|rejected|"
    r"remediated|resolved|no findings?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SufficiencyRequirement:
    name: str
    required_terms: tuple[str, ...]


class FusionEvidenceRetriever(EvidenceRetriever):
    strategy_name = "dense_sparse_score_fusion_sufficiency_v1"

    def __init__(
        self,
        encoder: DenseTextEncoder,
        *,
        minimum_dense_similarity: float = 0.0,
        sparse_weight: float = 0.15,
        cache_queries: bool = True,
        chunk_words: int = 120,
        overlap_words: int = 30,
    ) -> None:
        super().__init__(chunk_words=chunk_words, overlap_words=overlap_words)
        if not -1.0 <= minimum_dense_similarity <= 1.0:
            raise ValueError("minimum_dense_similarity must be between -1 and 1.")
        if not 0.0 <= sparse_weight <= 1.0:
            raise ValueError("sparse_weight must be between 0 and 1.")
        self.minimum_dense_similarity = minimum_dense_similarity
        self.sparse_weight = sparse_weight
        self.dense_weight = 1.0 - sparse_weight
        self.dense = DenseEvidenceRetriever(
            encoder,
            minimum_similarity=-1.0,
            cache_queries=cache_queries,
            chunk_words=chunk_words,
            overlap_words=overlap_words,
        )
        self.sparse = HybridEvidenceRetriever(
            chunk_words=chunk_words,
            overlap_words=overlap_words,
        )

    @property
    def model_name(self) -> str:
        return self.dense.model_name

    @property
    def embedding_dimension(self) -> int:
        return self.dense.embedding_dimension

    def prepare_documents(
        self,
        documents: list[SearchDocument],
    ) -> DensePreparation:
        return self.dense.prepare_documents(documents)

    def search(
        self,
        *,
        query: str,
        documents: list[SearchDocument],
        top_k: int = 3,
    ) -> RetrievalRun:
        preparation = self.dense.prepare_documents(documents)
        if preparation.chunk_count == 0:
            return RetrievalRun(total_chunks=0, results=())

        dense_run = self.dense.search(
            query=query,
            documents=documents,
            top_k=preparation.chunk_count,
        )
        sparse_run = self.sparse.search(
            query=query,
            documents=documents,
            top_k=preparation.chunk_count,
        )
        if sparse_run.abstention_reason:
            return RetrievalRun(
                total_chunks=dense_run.total_chunks,
                results=(),
                abstention_reason=sparse_run.abstention_reason,
                required_terms=sparse_run.required_terms,
            )

        requirement = self._sufficiency_requirement(query)
        dense_by_chunk = {result.chunk_id: result for result in dense_run.results}
        sparse_by_chunk = {result.chunk_id: result for result in sparse_run.results}
        maximum_sparse = max(
            (result.rerank_score for result in sparse_run.results),
            default=0.0,
        )

        ranked: list[RankedEvidenceChunk] = []
        for chunk_id, dense_result in dense_by_chunk.items():
            sparse_result = sparse_by_chunk.get(chunk_id)
            dense_supported = (
                dense_result.rerank_score >= self.minimum_dense_similarity
            )
            sparse_supported = bool(
                sparse_result
                and sparse_result.relevance_label in {"strong", "supporting"}
            )
            if not dense_supported and not sparse_supported:
                continue
            if requirement and not self._supports_requirement(
                dense_result.content,
                requirement,
            ):
                continue

            normalized_sparse = (
                sparse_result.rerank_score / maximum_sparse
                if sparse_result and maximum_sparse
                else 0.0
            )
            fusion_score = (
                self.dense_weight * dense_result.rerank_score
                + self.sparse_weight * normalized_sparse
            )
            sparse_terms = sparse_result.matched_terms if sparse_result else ()
            matched_terms = tuple(
                dict.fromkeys((*dense_result.matched_terms, *sparse_terms))
            )
            ranked.append(
                RankedEvidenceChunk(
                    chunk_id=dense_result.chunk_id,
                    source_id=dense_result.source_id,
                    citation_id=dense_result.citation_id,
                    filename=dense_result.filename,
                    chunk_index=dense_result.chunk_index,
                    content=dense_result.content,
                    retrieval_score=dense_result.rerank_score,
                    rerank_score=round(fusion_score, 6),
                    matched_terms=matched_terms,
                    relevance_label=(
                        sparse_result.relevance_label
                        if sparse_result
                        else "dense_only"
                    ),
                    core_matches=(
                        sparse_result.core_matches if sparse_result else ()
                    ),
                )
            )

        ranked.sort(
            key=lambda result: (
                -result.rerank_score,
                -result.retrieval_score,
                result.source_id,
                result.chunk_index,
            )
        )
        if not ranked:
            return RetrievalRun(
                total_chunks=dense_run.total_chunks,
                results=(),
                abstention_reason=(
                    "answer_slot_not_supported"
                    if requirement
                    else "fusion_evidence_sufficiency_not_met"
                ),
                required_terms=(requirement.required_terms if requirement else ()),
            )
        return RetrievalRun(
            total_chunks=dense_run.total_chunks,
            results=tuple(ranked[:top_k]),
            required_terms=(requirement.required_terms if requirement else ()),
        )

    def _sufficiency_requirement(
        self,
        query: str,
    ) -> SufficiencyRequirement | None:
        if QUESTION_ACTOR.search(query) and AUTHORIZATION_QUERY.search(query):
            return SufficiencyRequirement(
                name="authorization_actor",
                required_terms=("approval",),
            )
        if OUTCOME_QUERY.search(query):
            return SufficiencyRequirement(
                name="outcome_status",
                required_terms=("outcome_status",),
            )
        return None

    def _supports_requirement(
        self,
        content: str,
        requirement: SufficiencyRequirement,
    ) -> bool:
        if requirement.name == "authorization_actor":
            return "approval" in self.tokenize(content)
        if requirement.name == "outcome_status":
            return bool(OUTCOME_STATUS.search(content))
        raise ValueError(f"Unknown sufficiency requirement '{requirement.name}'.")
