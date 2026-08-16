from collections import Counter
import math
import re

from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import RankedEvidenceChunk
from app.services.retrieval import RetrievalRun
from app.services.retrieval import SearchDocument


CONCEPT_ALIASES = {
    "accountability": "owner",
    "accountable": "owner",
    "responsibility": "owner",
    "responsible": "owner",
    "backout": "rollback",
    "fallback": "rollback",
    "revert": "rollback",
    "reverted": "rollback",
    "reverting": "rollback",
    "reversion": "rollback",
    "deployment": "release",
    "deployments": "release",
    "deploy": "release",
    "launch": "release",
    "rollout": "release",
    "rollouts": "release",
    "clearance": "approval",
    "permission": "access",
    "permissions": "access",
    "entitlement": "access",
    "entitlements": "access",
    "sign-off": "approval",
    "signoff": "approval",
    "authorize": "approval",
    "deterioration": "error",
    "deteriorates": "error",
    "failure": "error",
    "failures": "error",
    "degradation": "error",
    "compliance": "security",
    "privacy": "security",
    "retention": "security",
    "subprocessor": "security",
    "subprocessors": "security",
    "purchasing": "procurement",
    "purchase": "procurement",
    "commercial": "contract",
    "terms": "contract",
    "blocked": "blocker",
    "blockers": "blocker",
    "cannot": "blocker",
    "incomplete": "blocker",
    "missing": "blocker",
    "unanswered": "blocker",
}
CORE_CONCEPTS = {
    "access",
    "approval",
    "blocker",
    "contract",
    "error",
    "owner",
    "procurement",
    "readiness",
    "release",
    "rollback",
    "security",
}
RELEVANCE_TIERS = {
    "strong": 2,
    "supporting": 1,
    "weak": 0,
}
CONCEPT_PHRASES = (
    (re.compile(r"\bsupport[\s_-]+coverage\b", re.IGNORECASE), "readiness"),
)


class HybridEvidenceRetriever(EvidenceRetriever):
    strategy_name = "deterministic_bm25_concept_vector_hybrid_v3"
    lexical_weight = 0.15
    concept_weight = 0.80
    filename_weight = 0.05

    def search(
        self,
        *,
        query: str,
        documents: list[SearchDocument],
        top_k: int = 3,
    ) -> RetrievalRun:
        chunks = self.chunk_documents(documents)
        query_vector = Counter(self.query_terms(query))
        if not chunks or not query_vector:
            return RetrievalRun(total_chunks=len(chunks), results=())
        required_terms = self._required_concepts(query)
        required_set = set(required_terms)
        query_core_concepts = tuple(
            concept
            for concept in query_vector
            if concept in CORE_CONCEPTS
        )

        lexical = super()._search_chunks(
            query=query,
            chunks=chunks,
            top_k=max(len(chunks), 1),
        )
        lexical_by_chunk = {result.chunk_id: result for result in lexical.results}
        maximum_lexical_score = max(
            (result.rerank_score for result in lexical.results),
            default=0.0,
        )

        ranked: list[RankedEvidenceChunk] = []
        for chunk in chunks:
            chunk_concepts = self._concept_tokens(chunk.content)
            chunk_vector = Counter(tuple(dict.fromkeys(chunk_concepts)))
            concept_similarity = self._cosine_similarity(query_vector, chunk_vector)
            lexical_result = lexical_by_chunk.get(chunk.chunk_id)
            lexical_score = lexical_result.rerank_score if lexical_result else 0.0
            normalized_lexical = (
                lexical_score / maximum_lexical_score
                if maximum_lexical_score
                else 0.0
            )
            filename_similarity = self._cosine_similarity(
                query_vector,
                Counter(self.query_terms(chunk.filename)),
            )
            hybrid_score = (
                self.lexical_weight * normalized_lexical
                + self.concept_weight * concept_similarity
                + self.filename_weight * filename_similarity
            )
            if hybrid_score <= 0:
                continue

            matched_concepts = tuple(
                concept
                for concept in dict.fromkeys(query_vector)
                if concept in chunk_vector
            )
            core_matches = tuple(
                concept
                for concept in query_core_concepts
                if concept in chunk_vector
            )
            if len(core_matches) >= 2 or (
                required_set and required_set <= set(matched_concepts)
            ):
                relevance_label = "strong"
            elif core_matches:
                relevance_label = "supporting"
            else:
                relevance_label = "weak"
            ranked.append(
                RankedEvidenceChunk(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    citation_id=chunk.citation_id,
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    retrieval_score=(
                        lexical_result.retrieval_score
                        if lexical_result
                        else 0.0
                    ),
                    rerank_score=round(hybrid_score, 6),
                    matched_terms=matched_concepts,
                    relevance_label=relevance_label,
                    core_matches=core_matches,
                )
            )

        ranked.sort(
            key=lambda result: (
                -RELEVANCE_TIERS[result.relevance_label],
                -len(result.core_matches),
                -result.rerank_score,
                -result.retrieval_score,
                result.source_id,
                result.chunk_index,
            )
        )
        if required_terms:
            ranked = [
                result
                for result in ranked
                if required_set <= set(result.matched_terms)
            ]
            if not ranked:
                return RetrievalRun(
                    total_chunks=len(chunks),
                    results=(),
                    abstention_reason="compound_intent_not_supported",
                    required_terms=required_terms,
                )
        return RetrievalRun(
            total_chunks=len(chunks),
            results=tuple(ranked[:top_k]),
            required_terms=required_terms,
        )

    def _concept_tokens(self, value: str) -> tuple[str, ...]:
        for pattern, replacement in CONCEPT_PHRASES:
            value = pattern.sub(replacement, value)
        return tuple(
            CONCEPT_ALIASES.get(token, token)
            for token in self.tokenize(value)
        )

    def query_terms(self, value: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._concept_tokens(value)))

    def _required_concepts(self, query: str) -> tuple[str, ...]:
        concepts = set(self.query_terms(query))
        normalized_query = query.casefold()
        compound_cues = (
            "accountable",
            "accountability",
            "conflict",
            "disagree",
            "responsible",
            "who",
        )
        if not any(cue in normalized_query for cue in compound_cues):
            return ()
        if {"owner", "rollback"} <= concepts:
            return ("owner", "rollback")
        if "approval" in concepts:
            for action in ("rollback", "access", "release", "security", "procurement"):
                if action in concepts:
                    return ("approval", action)
        return ()

    @staticmethod
    def _cosine_similarity(
        left: Counter[str],
        right: Counter[str],
    ) -> float:
        if not left or not right:
            return 0.0
        dot_product = sum(count * right.get(term, 0) for term, count in left.items())
        if dot_product == 0:
            return 0.0
        left_norm = math.sqrt(sum(count * count for count in left.values()))
        right_norm = math.sqrt(sum(count * count for count in right.values()))
        return dot_product / (left_norm * right_norm)
