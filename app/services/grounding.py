from dataclasses import dataclass
import re

from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import SearchDocument


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
MIN_GROUNDED_QUERY_COVERAGE = 0.4
MAX_CLAIM_CHARACTERS = 600
ANSWERER_NAME = "deterministic_extractive_grounding_v2"


@dataclass(frozen=True)
class GroundedClaim:
    claim_id: str
    text: str
    source_id: str
    citation_id: str
    filename: str
    chunk_id: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class GroundedAnswerRun:
    status: str
    answer: str
    source_count: int
    total_chunks: int
    query_term_coverage: float
    claims: tuple[GroundedClaim, ...]
    abstention_reason: str | None = None
    required_terms: tuple[str, ...] = ()
    context_policy: str = "all_ranked"
    excluded_result_count: int = 0


class GroundedAnswerService:
    def __init__(self, retriever: EvidenceRetriever | None = None) -> None:
        self.retriever = retriever or EvidenceRetriever()

    def answer(
        self,
        *,
        query: str,
        documents: list[SearchDocument],
        top_k: int = 3,
        max_claims: int = 5,
    ) -> GroundedAnswerRun:
        retrieval = self.retriever.search(
            query=query,
            documents=documents,
            top_k=top_k,
        )
        strong_results = tuple(
            result
            for result in retrieval.results
            if result.relevance_label == "strong"
        )
        supporting_results = tuple(
            result
            for result in retrieval.results
            if result.relevance_label == "supporting"
        )
        answer_results = retrieval.results
        context_policy = "all_ranked"
        if strong_results:
            covered_core_concepts = {
                concept
                for result in strong_results
                for concept in result.core_matches
            }
            covered_query_terms = {
                term
                for result in strong_results
                for term in result.matched_terms
            }
            complementary_results = []
            for result in retrieval.results:
                if result.relevance_label != "supporting":
                    continue
                new_core_concepts = set(result.core_matches) - covered_core_concepts
                new_non_core_terms = (
                    set(result.matched_terms)
                    - set(result.core_matches)
                    - covered_query_terms
                )
                if not new_core_concepts or not new_non_core_terms:
                    continue
                complementary_results.append(result)
                covered_core_concepts.update(new_core_concepts)
                covered_query_terms.update(result.matched_terms)

            selected_chunk_ids = {
                result.chunk_id
                for result in (*strong_results, *complementary_results)
            }
            answer_results = tuple(
                result
                for result in retrieval.results
                if result.chunk_id in selected_chunk_ids
            )
            if complementary_results:
                context_policy = "strong_plus_supporting"
            elif len(strong_results) < len(retrieval.results):
                context_policy = "strong_only"
        elif supporting_results and len(supporting_results) < len(retrieval.results):
            answer_results = supporting_results
            context_policy = "supporting_only"
        excluded_result_count = len(retrieval.results) - len(answer_results)
        query_terms = set(self.retriever.query_terms(query))
        matched_terms = {
            term
            for result in answer_results
            for term in result.matched_terms
        }
        coverage = len(matched_terms) / len(query_terms) if query_terms else 0.0
        compound_intent_supported = bool(retrieval.required_terms) and (
            set(retrieval.required_terms) <= matched_terms
        )
        strong_context_supported = bool(strong_results)

        claims: list[GroundedClaim] = []
        seen_claims: set[tuple[str, str]] = set()
        for result in answer_results:
            result_terms = set(result.matched_terms)
            sentences = self._sentences(result.content)
            sentences.sort(
                key=lambda sentence: (
                    -len(result_terms & set(self.retriever.tokenize(sentence))),
                    result.content.find(sentence),
                )
            )
            claims_from_result = 0
            for sentence in sentences:
                sentence_terms = tuple(
                    term
                    for term in result.matched_terms
                    if term in self.retriever.query_terms(sentence)
                )
                claim_text = self._bounded_claim(sentence)
                claim_key = (result.source_id, claim_text.casefold())
                if claim_key in seen_claims:
                    continue
                seen_claims.add(claim_key)
                claims.append(
                    GroundedClaim(
                        claim_id=f"claim-{len(claims) + 1}",
                        text=claim_text,
                        source_id=result.source_id,
                        citation_id=result.citation_id,
                        filename=result.filename,
                        chunk_id=result.chunk_id,
                        matched_terms=sentence_terms,
                    )
                )
                claims_from_result += 1
                if len(claims) >= max_claims or claims_from_result >= 3:
                    break
            if len(claims) >= max_claims:
                break

        if not claims:
            status = "insufficient_evidence"
            if retrieval.abstention_reason and retrieval.required_terms:
                required = " + ".join(retrieval.required_terms)
                answer = (
                    "I couldn't find a single passage supporting the required "
                    f"concepts together: {required}. Attach or request a source "
                    "that directly addresses them."
                )
            else:
                answer = (
                    "I couldn't find support for this request in the attached evidence. "
                    "Attach or request a source that directly addresses it."
                )
        elif (
            coverage >= MIN_GROUNDED_QUERY_COVERAGE
            or compound_intent_supported
            or strong_context_supported
        ):
            status = "grounded"
            answer = self._format_answer(
                "The attached evidence supports these findings:",
                claims,
            )
        else:
            status = "partial_evidence"
            answer = self._format_answer(
                (
                    "The attached evidence provides partial support, "
                    "but does not fully answer the request:"
                ),
                claims,
                footer="Additional evidence is required before treating the request as resolved.",
            )

        return GroundedAnswerRun(
            status=status,
            answer=answer,
            source_count=len(documents),
            total_chunks=retrieval.total_chunks,
            query_term_coverage=round(coverage, 4),
            claims=tuple(claims),
            abstention_reason=retrieval.abstention_reason,
            required_terms=retrieval.required_terms,
            context_policy=context_policy,
            excluded_result_count=excluded_result_count,
        )

    @staticmethod
    def _sentences(content: str) -> list[str]:
        return [
            sentence.strip()
            for sentence in SENTENCE_BOUNDARY.split(content)
            if sentence.strip()
        ]

    @staticmethod
    def _bounded_claim(sentence: str) -> str:
        if len(sentence) <= MAX_CLAIM_CHARACTERS:
            return sentence
        boundary = sentence.rfind(" ", 0, MAX_CLAIM_CHARACTERS + 1)
        return sentence[: boundary if boundary > 0 else MAX_CLAIM_CHARACTERS].rstrip()

    @staticmethod
    def _format_answer(
        heading: str,
        claims: list[GroundedClaim],
        *,
        footer: str | None = None,
    ) -> str:
        lines = [heading]
        lines.extend(f"- {claim.text} [{claim.citation_id}]" for claim in claims)
        if footer:
            lines.append(footer)
        return "\n".join(lines)
