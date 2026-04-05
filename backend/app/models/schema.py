"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# Chat Models
class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None
    # Multimodal support
    has_image: bool = Field(False, description="Whether this message contains an image")
    image_data: Optional[str] = Field(None, description="Base64 encoded image data")
    image_format: Optional[str] = Field(None, description="Image format (png, jpeg, webp, etc.)")
    has_file: bool = Field(False, description="Whether this message contains a file attachment")
    file_name: Optional[str] = Field(None, description="Uploaded file name")
    file_format: Optional[str] = Field(None, description="Uploaded file format/extension")
    reasoning_content: Optional[str] = Field(None, description="Structured reasoning content when thinking is enabled")
    final_content: Optional[str] = Field(None, description="Structured final answer content")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field("", description="User message (optional when image is provided)")
    session_id: Optional[str] = Field(None, description="Session identifier for conversation history")
    use_search: bool = Field(False, description="Whether to use web search")
    stream: bool = Field(True, description="Whether to stream the response")
    # Multimodal support
    image: Optional[str] = Field(None, description="Base64 encoded image data (optional)")
    image_format: Optional[str] = Field(
        None,
        description="Image format/extension (png, jpeg, jpg, webp, gif, etc.)"
    )
    file: Optional[str] = Field(None, description="Base64 encoded file data (optional)")
    file_name: Optional[str] = Field(None, description="Uploaded file name")
    file_format: Optional[str] = Field(None, description="Uploaded file extension/format")
    enable_thinking: bool = Field(False, description="Enable Gemma4 thinking mode when supported")
    enable_tool_calling: bool = Field(False, description="Enable tool calling mode when supported")
    deploy_profile: Optional[str] = Field(
        None,
        description="Optional runtime profile override: rag_text | vision | full | benchmark",
    )

    @model_validator(mode="after")
    def validate_multimodal_input(self) -> "ChatRequest":
        """Allow image-only requests and normalize empty image prompts."""
        has_message = bool(self.message and self.message.strip())
        has_image = bool(self.image and self.image.strip())
        has_file = bool(self.file and self.file.strip())

        if not has_message and not has_image and not has_file:
            raise ValueError("At least one of message/image/file must be provided")

        if has_image and not has_message:
            # Keep backend behavior stable for image-only chat.
            self.message = "请描述这张图片"
        elif has_file and not has_message:
            # Keep file-only chat requests usable.
            hint_name = self.file_name or "这个文件"
            self.message = f"请阅读并总结{hint_name}的重点内容"

        if self.deploy_profile:
            normalized = self.deploy_profile.strip().lower()
            if normalized not in {"rag_text", "vision", "full", "benchmark"}:
                raise ValueError("deploy_profile must be one of: rag_text, vision, full, benchmark")
            self.deploy_profile = normalized

        return self


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


class DocumentBatchUploadResponse(BaseModel):
    """Response model for batch document upload."""

    documents: list[DocumentUploadResponse] = Field(..., description="Per-file upload results")
    total_files: int = Field(..., description="Total uploaded files")
    success_count: int = Field(..., description="Number of successfully processed files")
    failed_count: int = Field(..., description="Number of failed files")
    total_chunks: int = Field(..., description="Total chunks from successful files")


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


class CapabilityCheckResult(BaseModel):
    """Capability probe result item."""

    name: str = Field(..., description="Capability name")
    passed: bool = Field(..., description="Whether capability check passed")
    detail: str = Field("", description="Short check detail")
    latency_s: float = Field(0.0, description="Check latency in seconds")


class PerformanceBenchmarkSummary(BaseModel):
    """Latest benchmark summary."""

    run_id: str = Field(..., description="Benchmark run directory name")
    generated_at: Optional[str] = Field(None, description="Report generation time")
    model: Optional[str] = Field(None, description="Benchmark model")
    concurrency: Optional[int] = Field(None, description="Concurrency used")
    requests: Optional[int] = Field(None, description="Total requests")
    stream: Optional[bool] = Field(None, description="Whether stream mode was used")
    success_rate_percent: float = Field(0.0, description="Success rate percentage")
    p95_latency_s: float = Field(0.0, description="P95 latency in seconds")
    avg_latency_s: float = Field(0.0, description="Average latency in seconds")
    request_throughput_rps: float = Field(0.0, description="Request throughput req/s")
    completion_token_throughput_tps: float = Field(0.0, description="Completion throughput tok/s")
    p95_ttft_s: float = Field(0.0, description="P95 TTFT in seconds")


class PerformanceStrictSuiteSummary(BaseModel):
    """Latest strict suite summary."""

    run_id: str = Field(..., description="Strict suite run directory name")
    generated_at: Optional[str] = Field(None, description="Report generation time")
    overall: str = Field("UNKNOWN", description="Overall status PASS/FAIL")
    pass_count: int = Field(0, description="Number of passed scenarios")
    fail_count: int = Field(0, description="Number of failed scenarios")
    total: int = Field(0, description="Total number of scenarios")


class PerformanceCapabilitySummary(BaseModel):
    """Latest capability probe summary."""

    run_id: str = Field(..., description="Capability probe run directory name")
    generated_at: Optional[str] = Field(None, description="Report generation time")
    passed: int = Field(0, description="Number of passed capabilities")
    total: int = Field(0, description="Total capabilities")
    checks: list[CapabilityCheckResult] = Field(default_factory=list, description="Capability checks")


class PerformanceOverviewResponse(BaseModel):
    """Performance overview payload for frontend dashboard."""

    generated_at: str = Field(..., description="Response generation time")
    provider: str = Field(..., description="Current backend provider")
    active_model: str = Field(..., description="Active model name")
    deploy_profile: str = Field(..., description="Current deploy profile")
    vllm_connected: bool = Field(..., description="Whether vLLM endpoint is reachable")
    vllm_reason: Optional[str] = Field(None, description="Reason when vLLM check fails")
    latest_benchmark: Optional[PerformanceBenchmarkSummary] = Field(
        None,
        description="Latest direct benchmark summary",
    )
    latest_strict_suite: Optional[PerformanceStrictSuiteSummary] = Field(
        None,
        description="Latest strict suite summary",
    )
    latest_capability_probe: Optional[PerformanceCapabilitySummary] = Field(
        None,
        description="Latest capability probe summary",
    )


class ChatModeConfigResponse(BaseModel):
    """Runtime mode config derived from current deploy profile."""

    provider: str = Field(..., description="Current backend provider")
    deploy_profile: str = Field(..., description="Current vLLM deploy profile")
    supports_image: bool = Field(..., description="Whether image mode is supported")
    supports_thinking: bool = Field(..., description="Whether thinking mode is supported")
    supports_tool_calling: bool = Field(..., description="Whether tool calling mode is supported")
    available_profiles: list[str] = Field(default_factory=list, description="Switchable profiles for current provider")
    configured_profile: Optional[str] = Field(None, description="Profile from backend .env")
    runtime_profile_override: Optional[str] = Field(None, description="Runtime profile selected via API/UI")
    profile_source: str = Field("unknown", description="Source of effective profile")


class ChatModeUpdateRequest(BaseModel):
    """Request model for updating chat runtime mode profile."""

    deploy_profile: str = Field(..., description="Target deploy profile: rag_text | vision | full | benchmark")


# Error Models
class ErrorResponse(BaseModel):
    """Response model for errors."""

    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
