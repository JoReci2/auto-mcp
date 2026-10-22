"""Small-corpus SQLite retrieval with atomic corpus snapshots."""

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from yamcps_rag_core.embeddings import Embedder, validate_vector
from yamcps_rag_core.models import Document, Passage, SearchHit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
    key TEXT PRIMARY KEY, corpus TEXT NOT NULL, payload TEXT NOT NULL,
    fingerprint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passages (
    id TEXT PRIMARY KEY, document_key TEXT NOT NULL REFERENCES documents(key) ON DELETE CASCADE,
    payload TEXT NOT NULL, vector TEXT NOT NULL
);
"""


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w]+(?:-[\w]+)*", text.casefold()))


def _score(tokens: set[str], text: str, vector: list[float], encoded_vector: str) -> float:
    lexical = len(tokens & _tokens(text)) / len(tokens)
    if not vector:
        return lexical
    stored: list[float] = json.loads(encoded_vector)
    cosine = sum(a * b for a, b in zip(vector, stored, strict=True)) / (
        math.sqrt(sum(x * x for x in vector)) * math.sqrt(sum(x * x for x in stored))
    )
    return 0.5 * lexical + 0.5 * max(0.0, cosine)


class Index:
    """One embedding configuration per database; read calls never create files."""

    def __init__(self, path: Path, embedder: Embedder | None = None) -> None:
        """Keep configuration without opening the database or loading models.

        Args:
            path: SQLite index location.
            embedder: Optional shared vector provider; None selects lexical search.
        """
        self.path = path.expanduser().absolute()
        self.embedder = embedder

    def _connect(self, *, write: bool = False) -> sqlite3.Connection:
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file():
            raise ValueError("Index missing; run yamcps-docs ingest first")
        suffix = "?mode=rwc" if write else "?mode=ro"
        connection = sqlite3.connect(self.path.as_uri() + suffix, uri=True, timeout=10)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            if write:
                connection.executescript(_SCHEMA)
                with connection:
                    connection.execute("INSERT OR IGNORE INTO settings VALUES ('format', '1')")
                    connection.execute(
                        "INSERT OR IGNORE INTO settings VALUES ('embedder', ?)",
                        (self.embedder.identity if self.embedder else "lexical-v1",),
                    )
            settings = dict(connection.execute("SELECT key, value FROM settings"))
            expected = self.embedder.identity if self.embedder else "lexical-v1"
            if settings.get("format") != "1" or settings.get("embedder") != expected:
                raise ValueError("Index configuration mismatch; use a new index or matching model")
        except Exception:
            connection.close()
            raise
        return connection

    def sync(
        self, corpus: str, documents: list[Document], *, chunk_size: int = 1200
    ) -> dict[str, int]:
        """Atomically replace one complete corpus snapshot and remove stale revisions.

        Args:
            corpus: Explicit synchronization scope, leaving other corpora untouched.
            documents: Complete source snapshot, including revisions to retain.
            chunk_size: Maximum characters per passage; minimum 64.

        Returns:
            Counts of updated, unchanged and deleted documents.

        Raises:
            ValueError: Invalid input, mixed corpus or incompatible embeddings.
        """
        if not corpus.strip() or not 64 <= chunk_size <= 16000:
            raise ValueError("Corpus is required and chunk_size must be between 64 and 16000")
        if any(d.corpus != corpus for d in documents):
            raise ValueError("All documents must belong to the synchronized corpus")
        if len({d.key for d in documents}) != len(documents):
            raise ValueError("Duplicate document revisions")
        with closing(self._connect(write=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = dict(
                db.execute("SELECT key, fingerprint FROM documents WHERE corpus = ?", (corpus,))
            )
            changed = unchanged = 0
            for document in documents:
                fingerprint = hashlib.sha256(
                    (document.model_dump_json() + f":chunks-v1:{chunk_size}").encode()
                ).hexdigest()
                if existing.get(document.key) == fingerprint:
                    unchanged += 1
                    continue
                self._replace(db, document, fingerprint, chunk_size)
                changed += 1
            removed = set(existing) - {d.key for d in documents}
            db.executemany("DELETE FROM documents WHERE key = ?", [(key,) for key in removed])
        return {"updated": changed, "unchanged": unchanged, "deleted": len(removed)}

    def _replace(
        self, db: sqlite3.Connection, document: Document, fingerprint: str, chunk_size: int
    ) -> None:
        db.execute("DELETE FROM documents WHERE key = ?", (document.key,))
        db.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (document.key, document.corpus, document.model_dump_json(), fingerprint),
        )
        timestamp = datetime.now(UTC).isoformat()
        for start in range(0, len(document.text), chunk_size):
            text = document.text[start : start + chunk_size]
            passage = Passage(
                passage_id=hashlib.sha256(
                    f"{document.key}:{fingerprint}:{start}".encode()
                ).hexdigest(),
                corpus=document.corpus,
                document_id=document.document_id,
                revision=document.revision,
                source_uri=document.source_uri,
                text=text,
                start=start,
                end=start + len(text),
                indexed_at=timestamp,
                metadata=document.metadata,
            )
            vector = self.embedder.embed(text) if self.embedder else []
            if self.embedder:
                validate_vector(vector)
                size = db.execute("SELECT value FROM settings WHERE key='dimensions'").fetchone()
                if size is not None and int(size[0]) != len(vector):
                    raise ValueError("Embedding dimension mismatch")
                db.execute(
                    "INSERT OR IGNORE INTO settings VALUES ('dimensions', ?)", (str(len(vector)),)
                )
            db.execute(
                "INSERT INTO passages VALUES (?, ?, ?, ?)",
                (passage.passage_id, document.key, passage.model_dump_json(), json.dumps(vector)),
            )

    def search(
        self, query: str, corpus: str, *, filters: dict[str, str] | None = None, limit: int = 5
    ) -> list[SearchHit]:
        """Rank passages within an explicit corpus and exact metadata filters.

        Args:
            query: Nonempty question or exact identifier, at most 4000 characters.
            corpus: Required corpus boundary.
            filters: Metadata key/value pairs, applied before scoring.
            limit: Result count, between 1 and 20.

        Returns:
            Ranked citations; lexical-only mode omits passages without token matches.

        Raises:
            ValueError: Invalid request or incompatible index/provider.
        """
        tokens = _tokens(query)
        if not tokens or len(query) > 4000 or not corpus.strip() or not 1 <= limit <= 20:
            raise ValueError("Provide a query, corpus and limit between 1 and 20")
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT p.payload, p.vector FROM passages p JOIN documents d "
                "ON d.key = p.document_key WHERE d.corpus = ?",
                (corpus,),
            ).fetchall()
            dimensions = db.execute("SELECT value FROM settings WHERE key='dimensions'").fetchone()
        vector = self.embedder.embed(query) if self.embedder else []
        if self.embedder:
            validate_vector(vector)
            if dimensions is not None and len(vector) != int(dimensions[0]):
                raise ValueError("Embedding dimension mismatch")
        hits = []
        for payload, encoded_vector in rows:
            passage = Passage.model_validate_json(payload)
            if any(passage.metadata.get(k) != v for k, v in (filters or {}).items()):
                continue
            score = _score(tokens, passage.text, vector, encoded_vector)
            if score > 0:
                hits.append(SearchHit(**passage.model_dump(), score=score))
        return sorted(hits, key=lambda h: (-h.score, h.passage_id))[:limit]

    def get_document(self, corpus: str, document_id: str, revision: str) -> Document:
        """Read a specific source revision.

        Args:
            corpus: Corpus boundary.
            document_id: Source identity.
            revision: Exact indexed revision.

        Returns:
            Indexed source, including complete extracted text.

        Raises:
            ValueError: The revision is not indexed.
        """
        key = Document(corpus=corpus, document_id=document_id, revision=revision, text="").key
        with closing(self._connect()) as db:
            row = db.execute("SELECT payload FROM documents WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise ValueError("Document revision not found")
        return Document.model_validate_json(row[0])

    def get_passage(self, passage_id: str) -> Passage:
        """Read a citation without interpreting its identifier as a filesystem path.

        Args:
            passage_id: Opaque identifier returned by search.

        Returns:
            Indexed passage and provenance.

        Raises:
            ValueError: The citation no longer exists.
        """
        with closing(self._connect()) as db:
            row = db.execute("SELECT payload FROM passages WHERE id = ?", (passage_id,)).fetchone()
        if row is None:
            raise ValueError("Passage not found; search again after reindexing")
        return Passage.model_validate_json(row[0])

    def status(self, corpus: str) -> dict[str, str | int | None]:
        """Report counts and the last changed passage timestamp.

        Args:
            corpus: Corpus boundary.

        Returns:
            Retrieval mode, counts and timestamp; no model or document paths.
        """
        with closing(self._connect()) as db:
            documents = db.execute(
                "SELECT count(*) FROM documents WHERE corpus = ?", (corpus,)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT p.payload FROM passages p JOIN documents d "
                "ON d.key=p.document_key WHERE d.corpus = ?",
                (corpus,),
            ).fetchall()
        passages = [Passage.model_validate_json(row[0]) for row in rows]
        return {
            "corpus": corpus,
            "mode": "hybrid" if self.embedder else "lexical",
            "documents": documents,
            "passages": len(passages),
            "last_changed_at": max((p.indexed_at for p in passages), default=None),
        }
