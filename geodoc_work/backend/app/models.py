from typing import Any, Literal

from pydantic import BaseModel, Field

ArtifactType = Literal["text", "table", "figure", "map"]
AnswerType = Literal["table", "text", "figure", "map", "mixed", "not_found"]
Confidence = Literal["high", "medium", "low"]


class DocumentArtifact(BaseModel):
    """Structured unit indexed by the RAG pipeline."""

    id: str | None = None
    document_id: str | None = None
    document_name: str | None = None
    page: int | None = None
    artifact_type: ArtifactType = "text"
    title: str | None = None
    caption: str | None = None
    text: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    bbox: list[float] | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceChunk(DocumentArtifact):
    """Backward-compatible name used by older UI/components."""

    pass


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    language: str = Field(default="ru", pattern="^(ru|kk)$")
    top_k: int | None = Field(default=None, ge=1, le=30)


class ChatResponse(BaseModel):
    answer_type: AnswerType = "text"
    answer_markdown: str
    # Backward-compatible alias for the old frontend.
    answer: str | None = None
    tables: list[DocumentArtifact] = Field(default_factory=list)
    figures: list[DocumentArtifact] = Field(default_factory=list)
    maps: list[DocumentArtifact] = Field(default_factory=list)
    sources: list[DocumentArtifact] = Field(default_factory=list)
    used_demo_mode: bool = False
    confidence: Confidence = "medium"
    missing_data: list[str] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    document_id: str | None = None
    filename: str
    status: str
    message: str
    artifacts: int = 0
    tables: int = 0
    figures: int = 0
    maps: int = 0
