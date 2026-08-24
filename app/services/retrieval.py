from collections import Counter
from dataclasses import dataclass
import math
import re


TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "applies",
    "are",
    "as",
    "at",
    "be",
    "by",
    "complete",
    "confirm",
    "coordinate",
    "did",
    "exact",
    "for",
    "from",
    "in",
    "identify",
    "is",
    "new",
    "next",
    "of",
    "on",
    "or",
    "prepare",
    "the",
    "they",
    "this",
    "to",
    "urgently",
    "what",
    "who",
    "with",
}
TOKEN_ALIASES = {
    "approvals": "approval",
    "approve": "approval",
    "approved": "approval",
    "authorized": "approval",
    "authorization": "approval",
    "commander": "owner",
    "errors": "error",
    "mitigation": "rollback",
    "owned": "owner",
    "ownership": "owner",
    "owns": "owner",
}


@dataclass(frozen=True)
class SearchDocument:
    source_id: str
    citation_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    source_id: str
    citation_id: str
    filename: str
    chunk_index: int
    content: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class RankedEvidenceChunk:
    chunk_id: str
    source_id: str
    citation_id: str
    filename: str
    chunk_index: int
    content: str
    retrieval_score: float
    rerank_score: float
    matched_terms: tuple[str, ...]
    relevance_label: str = "unscored"
    core_matches: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalRun:
    total_chunks: int
    results: tuple[RankedEvidenceChunk, ...]
    abstention_reason: str | None = None
    required_terms: tuple[str, ...] = ()


class EvidenceRetriever:
    strategy_name = "deterministic_bm25_lexical_reranker_v1"

    def __init__(self, chunk_words: int = 120, overlap_words: int = 30) -> None:
        if chunk_words < 20:
            raise ValueError("chunk_words must be at least 20.")
        if overlap_words < 0 or overlap_words >= chunk_words:
            raise ValueError("overlap_words must be non-negative and smaller than chunk_words.")
        self.chunk_words = chunk_words
        self.overlap_words = overlap_words

    def search(
        self,
        *,
        query: str,
        documents: list[SearchDocument],
        top_k: int = 3,
    ) -> RetrievalRun:
        chunks = self.chunk_documents(documents)
        return self._search_chunks(query=query, chunks=chunks, top_k=top_k)

    def _search_chunks(
        self,
        *,
        query: str,
        chunks: list[EvidenceChunk],
        top_k: int,
    ) -> RetrievalRun:
        query_tokens = self._tokenize(query)
        if not chunks or not query_tokens:
            return RetrievalRun(total_chunks=len(chunks), results=())

        document_frequency: Counter[str] = Counter()
        for chunk in chunks:
            document_frequency.update(set(chunk.tokens))
        average_length = sum(len(chunk.tokens) for chunk in chunks) / len(chunks)
        query_terms = tuple(dict.fromkeys(query_tokens))
        query_bigrams = set(zip(query_tokens, query_tokens[1:]))

        ranked: list[RankedEvidenceChunk] = []
        for chunk in chunks:
            term_frequency = Counter(chunk.tokens)
            matched_terms = tuple(term for term in query_terms if term in term_frequency)
            if not matched_terms:
                continue

            retrieval_score = sum(
                self._bm25_term_score(
                    term_frequency=term_frequency[term],
                    document_frequency=document_frequency[term],
                    document_count=len(chunks),
                    document_length=len(chunk.tokens),
                    average_length=average_length,
                )
                for term in query_terms
            )
            coverage = len(matched_terms) / len(query_terms)
            chunk_bigrams = set(zip(chunk.tokens, chunk.tokens[1:]))
            phrase_coverage = (
                len(query_bigrams & chunk_bigrams) / len(query_bigrams)
                if query_bigrams
                else 0.0
            )
            filename_tokens = set(self._tokenize(chunk.filename))
            filename_coverage = len(filename_tokens & set(query_terms)) / len(query_terms)
            rerank_score = (
                retrieval_score
                + (coverage * 1.5)
                + (phrase_coverage * 0.75)
                + (filename_coverage * 0.25)
            )
            ranked.append(
                RankedEvidenceChunk(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    citation_id=chunk.citation_id,
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    retrieval_score=round(retrieval_score, 6),
                    rerank_score=round(rerank_score, 6),
                    matched_terms=matched_terms,
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
        return RetrievalRun(total_chunks=len(chunks), results=tuple(ranked[:top_k]))

    def chunk_documents(self, documents: list[SearchDocument]) -> list[EvidenceChunk]:
        chunks: list[EvidenceChunk] = []
        step = self.chunk_words - self.overlap_words
        for document in documents:
            words = document.content.split()
            for chunk_index, start in enumerate(range(0, len(words), step)):
                chunk_words = words[start : start + self.chunk_words]
                if not chunk_words:
                    continue
                content = " ".join(chunk_words)
                chunks.append(
                    EvidenceChunk(
                        chunk_id=f"{document.source_id}-chunk-{chunk_index + 1}",
                        source_id=document.source_id,
                        citation_id=document.citation_id,
                        filename=document.filename,
                        chunk_index=chunk_index,
                        content=content,
                        tokens=tuple(self._tokenize(content)),
                    )
                )
                if start + self.chunk_words >= len(words):
                    break
        return chunks

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        value = re.sub(r"\broll\s+back\b", "rollback", value, flags=re.IGNORECASE)
        return [
            TOKEN_ALIASES.get(token, token)
            for token in TOKEN_PATTERN.findall(value.lower())
            if token not in STOP_WORDS and len(token) > 1
        ]

    def tokenize(self, value: str) -> tuple[str, ...]:
        return tuple(self._tokenize(value))

    def query_terms(self, value: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.tokenize(value)))

    @staticmethod
    def _bm25_term_score(
        *,
        term_frequency: int,
        document_frequency: int,
        document_count: int,
        document_length: int,
        average_length: float,
    ) -> float:
        if term_frequency == 0:
            return 0.0
        k1 = 1.5
        b = 0.75
        inverse_document_frequency = math.log(
            1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        length_normalization = k1 * (
            1 - b + b * (document_length / max(average_length, 1.0))
        )
        return inverse_document_frequency * (
            term_frequency * (k1 + 1) / (term_frequency + length_normalization)
        )
