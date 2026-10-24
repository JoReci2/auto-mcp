"""Structural contract for plugin-supplied retrieval backends."""

from typing import Protocol

from yamcps.rag.models import Document, Passage, SearchHit


class RetrievalIndex(Protocol):
    """Backend consumed by connectors; implementations own storage and retrieval."""

    def sync(
        self, corpus: str, documents: list[Document], *, chunk_size: int = 1200
    ) -> dict[str, int]:
        """Atomically replace a complete snapshot, retaining other corpora.

        Args:
            corpus: Explicit scope of the replacement.
            documents: Complete snapshot; an empty list clears this corpus.
            chunk_size: Maximum characters per passage, between 64 and 16000.

        Returns:
            Counts under updated, unchanged and deleted.

        Raises:
            ValueError: The snapshot or backend configuration is invalid.
        """
        ...

    def search(
        self, query: str, corpus: str, *, filters: dict[str, str] | None = None, limit: int = 5
    ) -> list[SearchHit]:
        """Return ranked passages within the requested corpus and filters.

        Args:
            query: Nonempty query, at most 4000 characters.
            corpus: Required corpus boundary.
            filters: Exact metadata equalities combined with AND.
            limit: Maximum results, between 1 and 20.

        Returns:
            Ranked citations, or an empty list when no passage matches.

        Raises:
            ValueError: The request or backend configuration is invalid.
        """
        ...

    def get_document(self, corpus: str, document_id: str, revision: str) -> Document:
        """Return one exact source revision.

        Args:
            corpus: Corpus boundary.
            document_id: Source identifier.
            revision: Exact revision to retrieve.

        Returns:
            Indexed document including its extracted text.

        Raises:
            ValueError: The revision is unavailable.
        """
        ...

    def get_passage(self, passage_id: str) -> Passage:
        """Resolve a citation previously returned by search.

        Args:
            passage_id: Opaque citation identifier.

        Returns:
            Passage including source reference and offsets.

        Raises:
            ValueError: The citation is unavailable.
        """
        ...

    def status(self, corpus: str) -> dict[str, str | int | None]:
        """Return corpus counts and backend status without credentials.

        Args:
            corpus: Corpus boundary.

        Returns:
            Corpus, mode, documents, passages and last_changed_at fields.
        """
        ...
