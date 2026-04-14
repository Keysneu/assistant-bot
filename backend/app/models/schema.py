"""Pydantic models for request/response validation."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator

_AUDIO_FILE_EXTENSIONS = {"wav", "mp3", "ogg", "webm", "m4a", "mp4", "flac"}


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
    image_id: Optional[str] = Field(None, description="Cached chat image identifier")
    image_ids: Optional[list[str]] = Field(None, description="Cached chat image identifiers for multi-image messages")
    has_file: bool = Field(False, description="Whether this message contains a file attachment")
    file_name: Optional[str] = Field(None, description="Uploaded file name")
    file_format: Optional[str] = Field(None, description="Uploaded file format/extension")
    has_audio: bool = Field(False, description="Whether this message contains an audio attachment")
    audio_url: Optional[str] = Field(None, description="Audio URL for multimodal transcription/understanding")
    audio_urls: Optional[list[str]] = Field(None, description="Multiple audio URLs for multimodal requests")
    has_video: bool = Field(False, description="Whether this message contains a video attachment")
    video_url: Optional[str] = Field(None, description="Video URL for multimodal understanding")
    video_urls: Optional[list[str]] = Field(None, description="Multiple video URLs for multimodal requests")
    reasoning_content: Optional[str] = Field(None, description="Structured reasoning content when thinking is enabled")
    final_content: Optional[str] = Field(None, description="Structured final answer content")
    tool_traces: Optional[list[dict]] = Field(None, description="Tool execution traces for assistant message")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field("", description="User message (optional when image/audio/file is provided)")
    session_id: Optional[str] = Field(None, description="Session identifier for conversation history")
    use_search: bool = Field(False, description="Whether to use web search")
    stream: bool = Field(True, description="Whether to stream the response")
    # Multimodal support
    image: Optional[str] = Field(None, description="Base64 encoded image data (optional)")
    image_id: Optional[str] = Field(None, description="Cached chat image ID (preferred over inline base64)")
    images: Optional[list[str]] = Field(None, description="Multiple base64 encoded image payloads (optional)")
    image_ids: Optional[list[str]] = Field(None, description="Multiple cached chat image IDs (preferred)")
    image_format: Optional[str] = Field(
        None,
        description="Image format/extension (png, jpeg, jpg, webp, gif, etc.)"
    )
    image_formats: Optional[list[str]] = Field(
        None,
        description="Image formats/extensions aligned with `images` list"
    )
    file: Optional[str] = Field(None, description="Base64 encoded file data (optional)")
    file_name: Optional[str] = Field(None, description="Uploaded file name")
    file_format: Optional[str] = Field(None, description="Uploaded file extension/format")
    audio_url: Optional[str] = Field(
        None,
        description="Audio URL for Gemma4 audio transcription/understanding (recommended: /api/chat/audios/{audio_id})",
    )
    audio_urls: Optional[list[str]] = Field(
        None,
        description="Multiple audio URLs for multimodal requests (recommended local uploaded URLs)",
    )
    video_url: Optional[str] = Field(
        None,
        description="Video URL for Gemma4 video understanding (recommended: /api/chat/videos/{video_id})",
    )
    video_urls: Optional[list[str]] = Field(
        None,
        description="Multiple video URLs for multimodal requests",
    )
    enable_thinking: bool = Field(False, description="Enable Gemma4 thinking mode when supported")
    enable_tool_calling: bool = Field(False, description="Enable tool calling mode when supported")
    response_format: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "OpenAI-compatible response_format for guided decoding. "
            "Example: {'type':'json_schema','json_schema':{'name':'x','schema':{...}}}"
        ),
    )
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        description="Optional per-request max_tokens override (bounded by backend MAX_TOKENS_HARD_LIMIT)",
    )
    temperature: Optional[float] = Field(
        None,
        ge=0.0,
        le=2.0,
        description="Optional per-request temperature override",
    )
    top_p: Optional[float] = Field(
        None,
        gt=0.0,
        le=1.0,
        description="Optional per-request top_p override",
    )
    deploy_profile: Optional[str] = Field(
        None,
        description="Deprecated: runtime profile override is ignored; server profile is fixed at startup",
    )

    def _resolve_attachment_format(self) -> str | None:
        """Best-effort resolve attachment extension for file-only inputs."""
        if self.file_format:
            normalized = self.file_format.strip().lower().lstrip(".")
            if normalized:
                return normalized

        if self.file_name:
            suffix = Path(self.file_name).suffix.lower().lstrip(".")
            if suffix:
                return suffix

        if self.file and self.file.startswith("data:") and "," in self.file:
            match = re.search(r"data:[^;/]+/([a-zA-Z0-9+.-]+);base64,", self.file)
            if match:
                return match.group(1).lower()

        return None

    def _is_audio_file_attachment(self) -> bool:
        """Whether `file` payload is actually an audio attachment."""
        file_payload = (self.file or "").strip()
        if not file_payload:
            return False
        if file_payload.startswith("data:audio/"):
            return True

        resolved_format = self._resolve_attachment_format()
        return bool(resolved_format and resolved_format in _AUDIO_FILE_EXTENSIONS)

    @model_validator(mode="after")
    def validate_multimodal_input(self) -> "ChatRequest":
        """Allow image-only requests and normalize empty image prompts."""
        normalized_images = [item.strip() for item in (self.images or []) if item and item.strip()]
        normalized_image_ids = [item.strip().lower() for item in (self.image_ids or []) if item and item.strip()]
        normalized_image_formats = [
            item.strip().lower().lstrip(".")
            for item in (self.image_formats or [])
            if item and item.strip()
        ]
        self.images = normalized_images or None
        self.image_ids = normalized_image_ids or None
        self.image_formats = normalized_image_formats or None
        self.audio_urls = [item.strip() for item in (self.audio_urls or []) if item and item.strip()] or None
        self.video_urls = [item.strip() for item in (self.video_urls or []) if item and item.strip()] or None

        if self.audio_url:
            self.audio_url = self.audio_url.strip()
            if not self.audio_url:
                self.audio_url = None
        if self.video_url:
            self.video_url = self.video_url.strip()
            if not self.video_url:
                self.video_url = None

        has_message = bool(self.message and self.message.strip())
        has_single_inline = bool(self.image and self.image.strip())
        has_single_cached = bool(self.image_id and self.image_id.strip())
        has_multi_inline = bool(self.images)
        has_multi_cached = bool(self.image_ids)
        has_image = bool(has_single_inline or has_single_cached or has_multi_inline or has_multi_cached)
        has_file = bool(self.file and self.file.strip())
        has_audio = bool(self.audio_url or self.audio_urls or self._is_audio_file_attachment())
        has_video = bool(self.video_url or self.video_urls)

        if not has_message and not has_image and not has_file and not has_audio and not has_video:
            raise ValueError("At least one of message/image/file/audio_url/video_url must be provided")

        if has_video and not has_message:
            self.message = (
                "请总结视频里发生了什么，并提取关键事件和时间线。"
                "如果视频中有人在提问，请直接回答该问题。"
            )
        elif has_audio and not has_message:
            # Audio is sent as native Gemma4 multimodal block; no extra emphasis needed.
            self.message = " "
        elif has_image and not has_message:
            # Keep backend behavior stable for image-only chat.
            self.message = "请描述这张图片"
        elif has_file and not has_message:
            # Keep file-only chat requests usable.
            hint_name = self.file_name or "这个文件"
            self.message = f"请阅读并总结{hint_name}的重点内容"

        if self.deploy_profile:
            normalized = self.deploy_profile.strip().lower()
            if normalized not in {"rag_text", "vision", "full", "full_featured", "benchmark", "extreme"}:
                raise ValueError(
                    "deploy_profile must be one of: rag_text, vision, full, full_featured, benchmark, extreme"
                )
            self.deploy_profile = normalized

        if self.image_id:
            self.image_id = self.image_id.strip().lower()

        if self.response_format is not None:
            if not isinstance(self.response_format, dict):
                raise ValueError("response_format must be a JSON object")
            format_type = str(self.response_format.get("type") or "").strip().lower()
            if format_type != "json_schema":
                raise ValueError("response_format.type currently only supports 'json_schema'")
            json_schema_obj = self.response_format.get("json_schema")
            if not isinstance(json_schema_obj, dict):
                raise ValueError("response_format.json_schema must be an object")
            schema_name = str(json_schema_obj.get("name") or "").strip()
            schema_body = json_schema_obj.get("schema")
            if not schema_name:
                raise ValueError("response_format.json_schema.name is required")
            if not isinstance(schema_body, dict):
                raise ValueError("response_format.json_schema.schema must be an object")
            self.response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema_body,
                },
            }

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


class ChatImageUploadResponse(BaseModel):
    """Response model for chat image upload endpoint."""

    image_id: str = Field(..., description="Cached image ID for subsequent chat requests")
    image_format: str = Field(..., description="Stored image format")
    size_bytes: int = Field(..., description="Stored image size in bytes")
    width: int = Field(..., description="Stored image width")
    height: int = Field(..., description="Stored image height")
    expires_in_seconds: int = Field(..., description="Cache TTL in seconds")


class ChatAudioUploadResponse(BaseModel):
    """Response model for chat audio upload endpoint."""

    audio_id: str = Field(..., description="Cached audio ID for subsequent chat requests")
    audio_format: str = Field(..., description="Stored audio format/extension")
    media_type: str = Field(..., description="Stored audio MIME type")
    size_bytes: int = Field(..., description="Stored audio size in bytes")
    file_name: Optional[str] = Field(None, description="Original uploaded audio file name")
    expires_in_seconds: int = Field(..., description="Cache TTL in seconds")


class ChatVideoUploadResponse(BaseModel):
    """Response model for chat video upload endpoint."""

    video_id: str = Field(..., description="Cached video ID for subsequent chat requests")
    video_format: str = Field(..., description="Stored video format/extension")
    media_type: str = Field(..., description="Stored video MIME type")
    size_bytes: int = Field(..., description="Stored video size in bytes")
    file_name: Optional[str] = Field(None, description="Original uploaded video file name")
    expires_in_seconds: int = Field(..., description="Cache TTL in seconds")


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
    supports_audio: bool = Field(..., description="Whether audio mode is supported")
    supports_video: bool = Field(..., description="Whether video mode is supported")
    supports_thinking: bool = Field(..., description="Whether thinking mode is supported")
    supports_tool_calling: bool = Field(..., description="Whether tool calling mode is supported")
    supports_structured_output: bool = Field(..., description="Whether JSON schema structured output is supported")
    available_profiles: list[str] = Field(default_factory=list, description="Reserved field; runtime profile switching disabled")
    configured_profile: Optional[str] = Field(None, description="Profile from backend .env")
    runtime_profile_override: Optional[str] = Field(None, description="Always null when runtime switching is disabled")
    profile_source: str = Field("unknown", description="Source of effective profile (env_locked/local_default)")


# Error Models
class ErrorResponse(BaseModel):
    """Response model for errors."""

    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
