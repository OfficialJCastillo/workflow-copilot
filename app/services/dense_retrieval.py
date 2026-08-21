from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Protocol

from app.services.retrieval import EvidenceChunk
from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import RankedEvidenceChunk
from app.services.retrieval import RetrievalRun
from app.services.retrieval import SearchDocument


DEFAULT_DENSE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class DenseTextEncoder(Protocol):
    model_name: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        ...


class FastEmbedTextEncoder:
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_DENSE_MODEL,
        cache_dir: str | Path | None = None,
        threads: int | None = None,
    ) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as error:
            raise RuntimeError(
                "Dense evaluation requires requirements-dense-eval.txt."
            ) from error

        supported = {
            model["model"]: model
            for model in TextEmbedding.list_supported_models()
        }
        if model_name not in supported:
            raise ValueError(f"Unsupported FastEmbed model '{model_name}'.")
        self.model_name = model_name
        self.dimension = int(supported[model_name]["dim"])
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=str(self.cache_dir) if self.cache_dir is not None else None,
            threads=threads,
        )

    @property
    def model_cache_size_bytes(self) -> int | None:
        if self.cache_dir is None:
            return None
        total = 0
        seen_files: set[tuple[int, int]] = set()
        for path in self.cache_dir.rglob("*"):
            if not path.is_file():
                continue
            details = path.stat()
            identity = (details.st_dev, details.st_ino)
            if identity in seen_files:
                continue
            seen_files.add(identity)
            total += details.st_size
        return total

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [
            tuple(float(value) for value in vector)
            for vector in self._model.embed(list(texts))
        ]


@dataclass(frozen=True)
class DensePreparation:
    fingerprint: str
    chunk_count: int
    cache_status: str
    embedding_dimension: int


class DenseEvidenceRetriever(EvidenceRetriever):
    strategy_name = "dense_cosine_threshold_v1"

    def __init__(
        self,
        encoder: DenseTextEncoder,
        *,
        minimum_similarity: float = 0.0,
        cache_queries: bool = True,
        chunk_words: int = 120,
        overlap_words: int = 30,
    ) -> None:
        super().__init__(chunk_words=chunk_words, overlap_words=overlap_words)
        if not -1.0 <= minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity must be between -1 and 1.")
        self.encoder = encoder
        self.minimum_similarity = minimum_similarity
        self.cache_queries = cache_queries
        self.corpus_cache_hits = 0
        self.corpus_cache_misses = 0
        self.query_cache_hits = 0
        self.query_cache_misses = 0
        self._corpus_cache: dict[
            str,
            tuple[tuple[EvidenceChunk, ...], tuple[tuple[float, ...], ...]],
        ] = {}
        self._query_cache: dict[str, tuple[float, ...]] = {}

    @property
    def model_name(self) -> str:
        return self.encoder.model_name

    @property
    def embedding_dimension(self) -> int:
        return self.encoder.dimension

    def prepare_documents(
        self,
        documents: list[SearchDocument],
    ) -> DensePreparation:
        fingerprint = self._corpus_fingerprint(documents)
        if fingerprint in self._corpus_cache:
            self.corpus_cache_hits += 1
            chunks, _ = self._corpus_cache[fingerprint]
            cache_status = "memory_hit"
        else:
            chunks = tuple(super().chunk_documents(documents))
            vectors = tuple(self.encoder.embed([chunk.content for chunk in chunks]))
            self._validate_vectors(vectors, len(chunks))
            self._corpus_cache[fingerprint] = (chunks, vectors)
            self.corpus_cache_misses += 1
            cache_status = "built"
        return DensePreparation(
            fingerprint=fingerprint,
            chunk_count=len(chunks),
            cache_status=cache_status,
            embedding_dimension=self.embedding_dimension,
        )

    def prepare_query(self, query: str) -> None:
        self._query_vector(query)

    def search(
        self,
        *,
        query: str,
        documents: list[SearchDocument],
        top_k: int = 3,
    ) -> RetrievalRun:
        fingerprint = self._corpus_fingerprint(documents)
        if fingerprint not in self._corpus_cache:
            self.prepare_documents(documents)
        else:
            self.corpus_cache_hits += 1
        chunks, vectors = self._corpus_cache[fingerprint]
        query_vector = self._query_vector(query)
        query_terms = tuple(dict.fromkeys(self.tokenize(query)))

        ranked = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            similarity = self._cosine_similarity(query_vector, vector)
            if similarity < self.minimum_similarity:
                continue
            matched_terms = tuple(
                term for term in query_terms if term in set(chunk.tokens)
            )
            ranked.append(
                RankedEvidenceChunk(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    citation_id=chunk.citation_id,
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    retrieval_score=round(similarity, 6),
                    rerank_score=round(similarity, 6),
                    matched_terms=matched_terms,
                    relevance_label="unscored",
                )
            )

        ranked.sort(
            key=lambda result: (
                -result.rerank_score,
                result.source_id,
                result.chunk_index,
            )
        )
        return RetrievalRun(
            total_chunks=len(chunks),
            results=tuple(ranked[:top_k]),
        )

    def _query_vector(self, query: str) -> tuple[float, ...]:
        if self.cache_queries:
            cached = self._query_cache.get(query)
            if cached is not None:
                self.query_cache_hits += 1
                return cached
        vectors = self.encoder.embed([query])
        self._validate_vectors(tuple(vectors), 1)
        vector = vectors[0]
        if self.cache_queries:
            self._query_cache[query] = vector
        self.query_cache_misses += 1
        return vector

    def _corpus_fingerprint(self, documents: list[SearchDocument]) -> str:
        payload = {
            "chunk_words": self.chunk_words,
            "overlap_words": self.overlap_words,
            "documents": [
                {
                    "source_id": document.source_id,
                    "citation_id": document.citation_id,
                    "filename": document.filename,
                    "content": document.content,
                }
                for document in sorted(
                    documents,
                    key=lambda item: (
                        item.source_id,
                        item.citation_id,
                        item.filename,
                        item.content,
                    ),
                )
            ],
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()

    def _validate_vectors(
        self,
        vectors: tuple[tuple[float, ...], ...],
        expected_count: int,
    ) -> None:
        if len(vectors) != expected_count:
            raise ValueError("Encoder returned an unexpected vector count.")
        if any(len(vector) != self.embedding_dimension for vector in vectors):
            raise ValueError("Encoder returned an unexpected embedding dimension.")

    @staticmethod
    def _cosine_similarity(
        left: tuple[float, ...],
        right: tuple[float, ...],
    ) -> float:
        if len(left) != len(right):
            raise ValueError("Dense vectors must have matching dimensions.")
        dot_product = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot_product / (left_norm * right_norm)
