"""Versioned source and citation contracts."""

import hashlib
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    """Immutable source revision; metadata is available for exact filtering."""

    model_config = ConfigDict(frozen=True)
    corpus: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    text: str
    source_namespace: str = Field(default="docs", pattern=r"^[a-z][a-z0-9-]*$")
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def source_uri(self) -> str:
        """Return a stable resource URI for this revision."""
        return f"{self.source_namespace}://source/" + "/".join(
            quote(part, safe="") for part in (self.corpus, self.document_id, self.revision)
        )

    @property
    def key(self) -> str:
        """Return a fixed-size source identity."""
        return hashlib.sha256(self.source_uri.encode()).hexdigest()


class Passage(BaseModel):
    """A bounded excerpt with offsets into the extracted source text."""

    passage_id: str
    corpus: str
    document_id: str
    revision: str
    source_uri: str
    text: str
    start: int
    end: int
    indexed_at: str
    metadata: dict[str, str]


class SearchHit(Passage):
    """Retrieved passage; score is ranking evidence, not a probability."""

    score: float
