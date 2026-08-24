from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import perf_counter

from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import EvidenceChunk
from app.services.retrieval import SearchDocument


SCHEMA = """
CREATE TABLE IF NOT EXISTS hybrid_corpora (
    fingerprint TEXT PRIMARY KEY,
    chunk_words INTEGER NOT NULL,
    overlap_words INTEGER NOT NULL,
    document_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hybrid_chunks (
    fingerprint TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    chunk_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    citation_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    tokens_json TEXT NOT NULL,
    PRIMARY KEY (fingerprint, ordinal),
    FOREIGN KEY (fingerprint) REFERENCES hybrid_corpora(fingerprint)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_hybrid_chunks_fingerprint
ON hybrid_chunks(fingerprint);

CREATE TABLE IF NOT EXISTS hybrid_namespaces (
    namespace TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    FOREIGN KEY (fingerprint) REFERENCES hybrid_corpora(fingerprint)
        ON DELETE CASCADE
);
"""


@dataclass(frozen=True)
class IndexPreparation:
    fingerprint: str
    chunk_count: int
    cache_status: str
    removed_corpus_count: int
    index_size_bytes: int


@dataclass(frozen=True)
class IndexCleanup:
    namespace: str
    removed_namespace_count: int
    removed_corpus_count: int
    index_size_bytes: int


@dataclass(frozen=True)
class IndexCompaction:
    before_bytes: int
    after_bytes: int
    reclaimed_bytes: int


class PersistentHybridEvidenceRetriever(HybridEvidenceRetriever):
    strategy_name = "deterministic_sqlite_persisted_hybrid_v1"

    def __init__(
        self,
        *,
        index_path: Path,
        chunk_words: int = 120,
        overlap_words: int = 30,
    ) -> None:
        super().__init__(chunk_words=chunk_words, overlap_words=overlap_words)
        self.index_path = Path(index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_cache_hits = 0
        self.disk_cache_hits = 0
        self.cache_misses = 0
        self.build_latencies_ms: list[float] = []
        self.disk_load_latencies_ms: list[float] = []
        self.compaction_count = 0
        self.last_compaction_reclaimed_bytes = 0
        self._memory_cache: dict[str, tuple[EvidenceChunk, ...]] = {}
        self._initialize_schema()

    def chunk_documents(self, documents: list[SearchDocument]) -> list[EvidenceChunk]:
        if not documents:
            return []
        fingerprint = self._corpus_fingerprint(documents)
        memory_chunks = self._memory_cache.get(fingerprint)
        if memory_chunks is not None:
            self.memory_cache_hits += 1
            return list(memory_chunks)

        load_started = perf_counter()
        persisted_chunks = self._load_chunks(fingerprint)
        if persisted_chunks:
            self.disk_load_latencies_ms.append(
                (perf_counter() - load_started) * 1_000
            )
            self.disk_cache_hits += 1
            self._memory_cache[fingerprint] = tuple(persisted_chunks)
            return persisted_chunks

        started = perf_counter()
        chunks = super().chunk_documents(documents)
        self._store_chunks(
            fingerprint=fingerprint,
            document_count=len(documents),
            chunks=chunks,
        )
        self.build_latencies_ms.append((perf_counter() - started) * 1_000)
        self.cache_misses += 1
        self._memory_cache[fingerprint] = tuple(chunks)
        return chunks

    @property
    def cache_hits(self) -> int:
        return self.memory_cache_hits + self.disk_cache_hits

    def prepare_documents(
        self,
        documents: list[SearchDocument],
        *,
        namespace: str,
        prune_stale: bool = True,
    ) -> IndexPreparation:
        fingerprint = self._corpus_fingerprint(documents)
        previous_memory_hits = self.memory_cache_hits
        previous_disk_hits = self.disk_cache_hits
        previous_misses = self.cache_misses
        chunks = self.chunk_documents(documents)
        if self.cache_misses > previous_misses:
            cache_status = "built"
        elif self.disk_cache_hits > previous_disk_hits:
            cache_status = "disk_hit"
        elif self.memory_cache_hits > previous_memory_hits:
            cache_status = "memory_hit"
        else:
            cache_status = "empty"
        removed_corpus_count = self._activate_namespace(
            namespace=namespace,
            fingerprint=fingerprint,
            prune_stale=prune_stale,
        )
        return IndexPreparation(
            fingerprint=fingerprint,
            chunk_count=len(chunks),
            cache_status=cache_status,
            removed_corpus_count=removed_corpus_count,
            index_size_bytes=self.index_size_bytes,
        )

    def clear_namespace(
        self,
        namespace: str,
        *,
        prune_stale: bool = True,
    ) -> IndexCleanup:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT fingerprint FROM hybrid_namespaces WHERE namespace = ?",
                (namespace,),
            ).fetchone()
            if existing is None:
                return IndexCleanup(
                    namespace=namespace,
                    removed_namespace_count=0,
                    removed_corpus_count=0,
                    index_size_bytes=self.index_size_bytes,
                )

            fingerprint = existing[0]
            namespace_result = connection.execute(
                "DELETE FROM hybrid_namespaces WHERE namespace = ?",
                (namespace,),
            )
            removed_corpus_count = 0
            if prune_stale:
                corpus_result = connection.execute(
                    """
                    DELETE FROM hybrid_corpora
                    WHERE fingerprint = ?
                      AND NOT EXISTS (
                          SELECT 1
                          FROM hybrid_namespaces
                          WHERE fingerprint = ?
                      )
                    """,
                    (fingerprint, fingerprint),
                )
                removed_corpus_count = corpus_result.rowcount
                if removed_corpus_count:
                    self._memory_cache.pop(fingerprint, None)

        return IndexCleanup(
            namespace=namespace,
            removed_namespace_count=namespace_result.rowcount,
            removed_corpus_count=removed_corpus_count,
            index_size_bytes=self.index_size_bytes,
        )

    def compact(self) -> IndexCompaction:
        before_bytes = self.index_size_bytes
        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute("VACUUM")
        finally:
            connection.close()
        after_bytes = self.index_size_bytes
        reclaimed_bytes = max(before_bytes - after_bytes, 0)
        self.compaction_count += 1
        self.last_compaction_reclaimed_bytes = reclaimed_bytes
        return IndexCompaction(
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            reclaimed_bytes=reclaimed_bytes,
        )

    @property
    def indexed_corpus_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM hybrid_corpora"
            ).fetchone()
        return int(row[0])

    @property
    def indexed_chunk_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM hybrid_chunks"
            ).fetchone()
        return int(row[0])

    @property
    def indexed_namespace_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM hybrid_namespaces"
            ).fetchone()
        return int(row[0])

    @property
    def index_size_bytes(self) -> int:
        return self.index_path.stat().st_size if self.index_path.exists() else 0

    def check_connection(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.index_path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

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

    def _load_chunks(self, fingerprint: str) -> list[EvidenceChunk]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    chunk_id,
                    source_id,
                    citation_id,
                    filename,
                    chunk_index,
                    content,
                    tokens_json
                FROM hybrid_chunks
                WHERE fingerprint = ?
                ORDER BY ordinal
                """,
                (fingerprint,),
            ).fetchall()
        return [
            EvidenceChunk(
                chunk_id=row[0],
                source_id=row[1],
                citation_id=row[2],
                filename=row[3],
                chunk_index=row[4],
                content=row[5],
                tokens=tuple(json.loads(row[6])),
            )
            for row in rows
        ]

    def _store_chunks(
        self,
        *,
        fingerprint: str,
        document_count: int,
        chunks: list[EvidenceChunk],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO hybrid_corpora (
                    fingerprint,
                    chunk_words,
                    overlap_words,
                    document_count
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    self.chunk_words,
                    self.overlap_words,
                    document_count,
                ),
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO hybrid_chunks (
                    fingerprint,
                    ordinal,
                    chunk_id,
                    source_id,
                    citation_id,
                    filename,
                    chunk_index,
                    content,
                    tokens_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        fingerprint,
                        ordinal,
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.citation_id,
                        chunk.filename,
                        chunk.chunk_index,
                        chunk.content,
                        json.dumps(chunk.tokens, separators=(",", ":")),
                    )
                    for ordinal, chunk in enumerate(chunks)
                ],
            )

    def _activate_namespace(
        self,
        *,
        namespace: str,
        fingerprint: str,
        prune_stale: bool,
    ) -> int:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT fingerprint FROM hybrid_namespaces WHERE namespace = ?",
                (namespace,),
            ).fetchone()
            previous_fingerprint = existing[0] if existing else None
            connection.execute(
                "DELETE FROM hybrid_namespaces WHERE namespace = ?",
                (namespace,),
            )
            connection.execute(
                """
                INSERT INTO hybrid_namespaces (namespace, fingerprint)
                VALUES (?, ?)
                """,
                (namespace, fingerprint),
            )
            removed_corpus_count = 0
            if (
                prune_stale
                and previous_fingerprint
                and previous_fingerprint != fingerprint
            ):
                result = connection.execute(
                    """
                    DELETE FROM hybrid_corpora
                    WHERE fingerprint = ?
                      AND NOT EXISTS (
                          SELECT 1
                          FROM hybrid_namespaces
                          WHERE fingerprint = ?
                      )
                    """,
                    (previous_fingerprint, previous_fingerprint),
                )
                removed_corpus_count = result.rowcount
                if removed_corpus_count:
                    self._memory_cache.pop(previous_fingerprint, None)
        return removed_corpus_count
