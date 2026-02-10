"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# Chat Models
class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., description="User message", min_length=1)
    session_id: Optional[str] = Field(None, description="Session identifier for conversation history")
    use_search: bool = Field(False, description="Whether to use web search")
    stream: bool = Field(True, description="Whether to stream the response")


class SessionTitleRequest(BaseModel):
    """Request model for updating session title."""

    title: str = Field(..., description="New title for the session", min_length=1)


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    content: str = Field(..., description="Assistant response")
    session_id: str = Field(..., description="Session identifier")
    sources: list[dict] = Field(default_factory=list, description="Source documents used")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class SourceDocument(BaseModel):
    """Source document reference."""

    content: str = Field(..., description="Document chunk content")
    metadata: dict = Field(..., description="Document metadata including source URL")
    score: Optional[float] = Field(None, description="Relevance score")


# Document Models
class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""

    document_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Processing status")
    chunk_count: int = Field(0, description="Number of chunks created")


class URLRequest(BaseModel):
    """Request model for URL ingestion."""

    urls: list[str] = Field(..., description="List of URLs to ingest", min_items=1)


class URLIngestResponse(BaseModel):
    """Response model for URL ingestion."""

    documents: list[DocumentUploadResponse] = Field(..., description="Processed documents")
    total_chunks: int = Field(..., description="Total chunks created")


# History Models
class HistoryResponse(BaseModel):
    """Response model for conversation history."""

    session_id: str = Field(..., description="Session identifier")
    messages: list[ChatMessage] = Field(..., description="Conversation history")


# Health Check
class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    model_loaded: bool = Field(False, description="Whether LLM is loaded")
    embedding_loaded: bool = Field(False, description="Whether embedding model is loaded")
    vector_db_ready: bool = Field(False, description="Whether vector DB is ready")


# Document List Models
class DocumentInfo(BaseModel):
    """Information about a single document."""

    document_id: str = Field(..., description="Document identifier")
    source: str = Field(..., description="Document source (filename or URL)")
    chunk_count: int = Field(..., description="Number of chunks")
    file_type: Optional[str] = Field(None, description="File extension")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class DocumentListResponse(BaseModel):
    """Response model for document list."""

    documents: list[DocumentInfo] = Field(..., description="List of documents")
    total_count: int = Field(..., description="Total number of documents")
    total_chunks: int = Field(..., description="Total number of chunks")


class DocumentDeleteResponse(BaseModel):
    """Response model for document deletion."""

    deleted: bool = Field(..., description="Whether deletion was successful")
    document_id: str = Field(..., description="Deleted document ID")
    chunks_removed: int = Field(..., description="Number of chunks removed")


# Error Models
class ErrorResponse(BaseModel):
    """Response model for errors."""

    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
