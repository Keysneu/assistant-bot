"""Chat API endpoints.

Handles streaming and non-streaming chat responses with RAG support.
Multimodal support for image understanding using BLIP-2 vision model.
"""
import base64
import json
import re
import logging
from threading import Lock
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from pypdf import PdfReader

from app.core.config import settings
from app.models.schema import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    SessionTitleRequest,
    ChatModeConfigResponse,
    ChatModeUpdateRequest,
)
from app.services.llm_service import (
    generate_response,
    astream_response,
    is_model_loaded,
    get_llm,
    get_active_model_name,
)
from app.services.rag_service import retrieve, get_context
from app.services.session_service import (
    create_session,
    add_message,
    get_context_for_query,
    get_all_sessions,
    get_session_info,
    update_session_title,
    clear_all_sessions,
)
from app.services.rag_service import verify_content_relevance
from app.services.vision_service import (
    analyze_image_content,
    is_vision_available,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

VLLM_PROFILE_CAPABILITIES: dict[str, dict[str, bool]] = {
    "rag_text": {
        "supports_image": False,
        "supports_thinking": True,
        "supports_tool_calling": False,
    },
    "vision": {
        "supports_image": True,
        "supports_thinking": True,
        "supports_tool_calling": False,
    },
    "full": {
        "supports_image": True,
        "supports_thinking": True,
        "supports_tool_calling": True,
    },
    "benchmark": {
        "supports_image": False,
        "supports_thinking": False,
        "supports_tool_calling": False,
    },
}

_RUNTIME_PROFILE_OVERRIDE: str | None = None
_RUNTIME_PROFILE_LOCK = Lock()


def _normalize_profile(profile: str | None) -> str | None:
    """Normalize profile key and validate against supported profile map."""
    if profile is None:
        return None
    normalized = profile.strip().lower()
    if not normalized:
        return None
    if normalized not in VLLM_PROFILE_CAPABILITIES:
        return None
    return normalized


def _get_runtime_profile_override() -> str | None:
    """Get runtime profile override set via API."""
    with _RUNTIME_PROFILE_LOCK:
        return _RUNTIME_PROFILE_OVERRIDE


def _set_runtime_profile_override(profile: str | None) -> None:
    """Set runtime profile override from API/UI."""
    global _RUNTIME_PROFILE_OVERRIDE
    with _RUNTIME_PROFILE_LOCK:
        _RUNTIME_PROFILE_OVERRIDE = profile


def _resolve_effective_profile(request_profile: str | None = None) -> tuple[str, str]:
    """Resolve effective profile and source for this request."""
    if settings.LLM_PROVIDER != "vllm":
        return "local_default", "local_default"

    normalized_request = _normalize_profile(request_profile)
    if normalized_request:
        return normalized_request, "request_override"

    runtime_override = _normalize_profile(_get_runtime_profile_override())
    if runtime_override:
        return runtime_override, "runtime_override"

    env_profile = _normalize_profile(settings.VLLM_DEPLOY_PROFILE)
    if env_profile:
        return env_profile, "env_default"

    return "rag_text", "fallback_default"


def _current_mode_config(request_profile: str | None = None) -> dict[str, object]:
    """Resolve runtime mode capability based on provider + effective profile."""
    if settings.LLM_PROVIDER != "vllm":
        return {
            "provider": settings.LLM_PROVIDER,
            "deploy_profile": "local_default",
            "supports_image": True,
            "supports_thinking": False,
            "supports_tool_calling": False,
            "available_profiles": [],
            "configured_profile": None,
            "runtime_profile_override": None,
            "profile_source": "local_default",
        }

    effective_profile, profile_source = _resolve_effective_profile(request_profile)
    caps = VLLM_PROFILE_CAPABILITIES[effective_profile]
    return {
        "provider": settings.LLM_PROVIDER,
        "deploy_profile": effective_profile,
        **caps,
        "available_profiles": list(VLLM_PROFILE_CAPABILITIES.keys()),
        "configured_profile": settings.VLLM_DEPLOY_PROFILE,
        "runtime_profile_override": _get_runtime_profile_override(),
        "profile_source": profile_source,
    }


def _resolve_mode_flags(request: ChatRequest) -> tuple[bool, bool, list[str], dict[str, object]]:
    """Resolve effective thinking/tool flags under current deploy profile."""
    mode_config = _current_mode_config(request.deploy_profile)
    supports_thinking = bool(mode_config.get("supports_thinking", False))
    supports_tool_calling = bool(mode_config.get("supports_tool_calling", False))

    warnings: list[str] = []
    if request.deploy_profile and str(mode_config.get("profile_source")) != "request_override":
        warnings.append(
            f"Requested profile '{request.deploy_profile}' is invalid; fallback to '{mode_config['deploy_profile']}'"
        )

    effective_thinking = bool(request.enable_thinking and supports_thinking)
    effective_tool_calling = bool(request.enable_tool_calling and supports_tool_calling)

    if request.enable_thinking and not effective_thinking:
        warnings.append(
            f"Thinking requested but disabled by deploy profile '{mode_config['deploy_profile']}'"
        )
    if request.enable_tool_calling and not effective_tool_calling:
        warnings.append(
            f"Tool calling requested but disabled by deploy profile '{mode_config['deploy_profile']}'"
        )

    if request.image and settings.LLM_PROVIDER == "vllm" and not bool(mode_config.get("supports_image", False)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Current deploy profile '{mode_config['deploy_profile']}' does not support image mode. "
                "Please switch runtime profile to 'vision' or 'full'."
            ),
        )

    return effective_thinking, effective_tool_calling, warnings, mode_config


def _extract_base64_payload(image_data: str) -> str:
    """Support both raw base64 and data URL image strings."""
    if image_data.startswith("data:image/") and "," in image_data:
        return image_data.split(",", 1)[1]
    return image_data


def _extract_file_payload(file_data: str) -> str:
    """Support both raw base64 and data URL file strings."""
    if file_data.startswith("data:") and "," in file_data:
        return file_data.split(",", 1)[1]
    return file_data


def _resolve_image_format(image_data: str | None, image_format: str | None) -> str | None:
    """Resolve image format from request payload or explicit field."""
    if image_format:
        return image_format
    if image_data and image_data.startswith("data:image/"):
        match = re.search(r"data:image/([a-zA-Z0-9+.-]+);base64,", image_data)
        if match:
            return match.group(1).lower()
    return None


def _resolve_file_format(
    file_name: str | None,
    file_data: str | None,
    file_format: str | None,
) -> str | None:
    """Resolve file extension from explicit field, file name, or data URL."""
    if file_format:
        return file_format.lower().lstrip(".")

    if file_name:
        suffix = Path(file_name).suffix.lower().lstrip(".")
        if suffix:
            return suffix

    if file_data and file_data.startswith("data:"):
        match = re.search(r"data:[^;/]+/([a-zA-Z0-9+.-]+);base64,", file_data)
        if match:
            return match.group(1).lower()
    return None


def _allowed_chat_file_extensions() -> set[str]:
    """Allowed chat attachment extensions."""
    values: set[str] = set()
    for item in settings.CHAT_FILE_ALLOWED_EXTENSIONS.split(","):
        ext = item.strip().lower().lstrip(".")
        if ext:
            values.add(ext)
    return values


def _enforce_image_payload_limit(image_data: str | None) -> None:
    """Protect tunnel/backends from oversized base64 image payloads."""
    if not image_data:
        return

    payload = _extract_base64_payload(image_data)
    if len(payload) > settings.MAX_IMAGE_BASE64_CHARS:
        approx_mb = len(payload) / 1024 / 1024
        limit_mb = settings.MAX_IMAGE_BASE64_CHARS / 1024 / 1024
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image payload too large ({approx_mb:.2f}MB base64). "
                f"Limit is {limit_mb:.2f}MB. Please upload a smaller image."
            ),
        )


def _enforce_file_payload_limit(file_data: str | None, file_name: str | None, file_format: str | None) -> str | None:
    """Protect backend from oversized/unsupported file attachments."""
    if not file_data:
        return None

    payload = _extract_file_payload(file_data)
    if len(payload) > settings.MAX_CHAT_FILE_BASE64_CHARS:
        approx_mb = len(payload) / 1024 / 1024
        limit_mb = settings.MAX_CHAT_FILE_BASE64_CHARS / 1024 / 1024
        raise HTTPException(
            status_code=413,
            detail=(
                f"File payload too large ({approx_mb:.2f}MB base64). "
                f"Limit is {limit_mb:.2f}MB."
            ),
        )

    resolved_format = _resolve_file_format(file_name=file_name, file_data=file_data, file_format=file_format)
    if not resolved_format:
        raise HTTPException(status_code=400, detail="无法识别文件格式，请提供 file_name 或 file_format")

    allowed = _allowed_chat_file_extensions()
    if resolved_format not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported chat file type '{resolved_format}'. Allowed: {', '.join(sorted(allowed))}",
        )

    return resolved_format


def _decode_file_text(file_payload: str, file_format: str) -> str:
    """Decode supported file attachments into plain text."""
    try:
        raw_bytes = base64.b64decode(file_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"文件 base64 解码失败: {exc}") from exc

    normalized_format = file_format.lower().lstrip(".")
    if normalized_format in {"pdf"}:
        try:
            reader = PdfReader(BytesIO(raw_bytes))
            texts: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    texts.append(page_text.strip())
            content = "\n\n".join(texts).strip()
            if not content:
                raise ValueError("PDF 中未提取到可读文本")
            return content
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF 解析失败: {exc}") from exc

    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise HTTPException(status_code=400, detail="文件解码失败，暂不支持该编码")


def _build_file_context(
    file_data: str | None,
    file_name: str | None,
    file_format: str | None,
) -> tuple[str, str | None]:
    """Parse chat attachment into prompt context block."""
    if not file_data:
        return "", None

    resolved_format = _enforce_file_payload_limit(file_data, file_name, file_format)
    payload = _extract_file_payload(file_data)
    file_text = _decode_file_text(payload, resolved_format or "")
    cleaned = file_text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="上传文件为空或无可读内容")

    max_chars = settings.MAX_CHAT_FILE_CONTEXT_CHARS
    truncated = cleaned[:max_chars]
    cut_note = ""
    if len(cleaned) > max_chars:
        cut_note = f"\n\n[文件内容过长，已截断到前 {max_chars} 字符]"

    display_name = file_name or f"attachment.{resolved_format}"
    context = f"【用户上传文件: {display_name}】\n{truncated}{cut_note}"
    return context, resolved_format


def _retrieve_rag_context(session_id: str, message: str, use_search: bool) -> tuple[str, list[dict]]:
    """Retrieve RAG context and normalized sources for a request."""
    sources = []
    rag_context = ""

    if use_search:
        return rag_context, sources

    try:
        query_with_context = get_context_for_query(session_id, message)
        documents = retrieve(query_with_context)
        if not documents:
            return rag_context, sources

        avg_score = sum(d.score or 0 for d in documents) / len(documents)
        score_check = avg_score > 0.4
        content_check = verify_content_relevance(message, documents)

        if score_check and content_check:
            rag_context = get_context(documents)
            sources = [
                {
                    "content": doc.content[:200] + "...",
                    "source": doc.metadata.get("source", "Unknown"),
                    "score": doc.score,
                }
                for doc in documents
            ]
    except Exception as exc:
        logger.warning(f"RAG retrieval failed: {exc}, continuing without context")

    return rag_context, sources


async def _analyze_image_with_vision_service(
    image_data: str | None,
    user_message: str,
) -> tuple[str, bool]:
    """Legacy vision path used for non-vLLM providers."""
    if not image_data:
        return "", False

    try:
        image_bytes = base64.b64decode(_extract_base64_payload(image_data))
    except Exception as exc:
        logger.error(f"Image decode failed: {exc}", exc_info=True)
        return "", False

    if not is_vision_available():
        logger.warning("Vision service not available, skipping image analysis")
        return "", False

    try:
        image_context = await analyze_image_content(image_bytes, user_question=user_message)
        return image_context, True
    except RuntimeError as vision_error:
        logger.warning(f"Vision service unavailable: {vision_error}, continuing without image analysis")
        return "", False
    except Exception as exc:
        logger.error(f"Vision processing failed: {exc}", exc_info=True)
        return "", False


def _merge_context(image_context: str, rag_context: str, file_context: str) -> str:
    """Merge image and RAG contexts into one prompt context block."""
    parts = []
    if image_context:
        parts.append(image_context)
    if rag_context:
        parts.append(rag_context)
    if file_context:
        parts.append(file_context)
    return "\n\n".join(parts)


def _score_reasoning_paragraph(paragraph: str) -> float:
    """Heuristic score: how likely this paragraph is planning/thinking content."""
    text = paragraph.strip()
    if not text:
        return 0.0

    score = 0.0
    if re.search(r"(thinking process|analyze the request|execution\s*-?\s*target|self-correction|review and formatting|strategy|target\s+\d)", text, re.IGNORECASE):
        score += 4.0
    if re.match(r"^\s*(\d{1,2}[.)]|(step|步骤)\s*\d+[:.)]?)", text, re.IGNORECASE):
        score += 3.0
    if re.search(r"\((self-correction|review|thinking)\b", text, re.IGNORECASE):
        score += 2.0
    if len(re.findall(r"[A-Za-z]", text)) > 40:
        score += 1.0
    return score


def _score_answer_paragraph(paragraph: str) -> float:
    """Heuristic score: how likely this paragraph is final user-facing answer."""
    text = paragraph.strip()
    if not text:
        return 0.0

    score = 0.0
    if re.search(r"(这是一个|以下是|下面是|终极答案|最终答案|第一部分|第二部分|第三部分|总结|结论|原句[:：]|^#{1,4}\s+|🌌|🌍|🗿)", text, re.IGNORECASE | re.MULTILINE):
        score += 4.0
    if re.search(r"\|[^|\n]+\|[^|\n]+\|", text):
        score += 2.0
    if len(re.findall(r"[\u3400-\u9fff]", text)) > max(5, len(text) * 0.2):
        score += 2.0
    if re.search(r"[。！？]", text):
        score += 1.0
    return score


def _split_reasoning_final_content(content: str, enable_thinking: bool) -> tuple[str | None, str]:
    """Split raw thought-style output into reasoning/final content for frontend rendering."""
    text = (content or "").strip()
    if not text:
        return None, ""
    if not enable_thinking:
        return None, text

    if not re.match(r"^thought\s*", text, flags=re.IGNORECASE):
        return None, text

    raw = re.sub(r"^thought\s*", "", text, count=1, flags=re.IGNORECASE).lstrip()
    if not raw:
        return None, ""

    # 1) Explicit markers
    markers = [
        r"this leads(?: directly)? to the detailed response provided below\.\)?",
        r"final output generation\.?\)?",
        r"(?:final answer|===\s*answer\s*===|最终回答|下面是(?:正式)?回答|以下是(?:详细)?回答)[:：]?",
    ]
    for marker in markers:
        match = re.search(marker, raw, flags=re.IGNORECASE)
        if match:
            reasoning = raw[: match.start()].strip()
            answer = re.sub(r"^[\s:：)\].-]+", "", raw[match.end():].strip())
            if answer:
                return reasoning, answer

    # 2) Explicit handoff line
    handoff = re.search(
        r"\((?:self-correction|the final output structure looks good|final output generation)[^)]+\)\s*",
        raw,
        flags=re.IGNORECASE,
    )
    if handoff:
        answer = raw[handoff.end():].strip()
        if answer:
            return raw[:handoff.end()].strip(), answer

    # 3) Scored paragraph boundary
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
    if len(paragraphs) >= 3:
        best_idx = -1
        best_score = float("-inf")
        for i in range(len(paragraphs) - 1):
            before = paragraphs[: i + 1]
            after = paragraphs[i + 1:]
            before_reason = sum(_score_reasoning_paragraph(p) for p in before)
            before_answer = sum(_score_answer_paragraph(p) for p in before)
            after_reason = sum(_score_reasoning_paragraph(p) for p in after)
            after_answer = sum(_score_answer_paragraph(p) for p in after)
            candidate = before_reason + after_answer - before_answer * 0.9 - after_reason * 0.6
            if candidate > best_score:
                best_score = candidate
                best_idx = i

        if best_idx >= 0 and best_score >= 3.2:
            reasoning = "\n\n".join(paragraphs[: best_idx + 1]).strip()
            answer = "\n\n".join(paragraphs[best_idx + 1:]).strip()
            if answer:
                return reasoning, answer

    # 4) Fallback: when split boundary is uncertain, avoid exposing ambiguous reasoning.
    # Keep all text as final content so frontend never mixes answer into a reasoning panel.
    return None, raw.strip()


@router.get("/mode-config", response_model=ChatModeConfigResponse)
async def get_chat_mode_config() -> ChatModeConfigResponse:
    """Get current runtime mode capabilities for chat UI."""
    return ChatModeConfigResponse(**_current_mode_config())


@router.put("/mode-config", response_model=ChatModeConfigResponse)
async def update_chat_mode_config(request: ChatModeUpdateRequest) -> ChatModeConfigResponse:
    """Update runtime chat profile from frontend selection."""
    if settings.LLM_PROVIDER != "vllm":
        return ChatModeConfigResponse(**_current_mode_config())

    normalized = _normalize_profile(request.deploy_profile)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="deploy_profile must be one of: rag_text, vision, full, benchmark",
        )

    _set_runtime_profile_override(normalized)
    logger.info("chat mode profile updated at runtime: %s", normalized)
    return ChatModeConfigResponse(**_current_mode_config())


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat request (non-streaming).

    Args:
        request: Chat request with message and session info

    Returns:
        Chat response with generated content and sources
    """
    # Trigger lazy loading if model not loaded
    if not is_model_loaded():
        try:
            get_llm()  # This will load the model
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Model loading failed: {str(e)}")

    _enforce_image_payload_limit(request.image)
    file_context, resolved_file_format = _build_file_context(
        file_data=request.file,
        file_name=request.file_name,
        file_format=request.file_format,
    )
    effective_thinking, effective_tool_calling, mode_warnings, mode_config = _resolve_mode_flags(request)

    # Create or use existing session
    session_id = request.session_id or create_session()

    image_format_to_store = _resolve_image_format(request.image, request.image_format)
    add_message(
        session_id,
        "user",
        request.message,
        has_image=bool(request.image),
        image_data=request.image,
        image_format=image_format_to_store,
        has_file=bool(request.file),
        file_name=request.file_name,
        file_format=resolved_file_format,
    )

    rag_context, sources = _retrieve_rag_context(
        session_id=session_id,
        message=request.message,
        use_search=request.use_search,
    )

    use_native_vllm_multimodal = settings.LLM_PROVIDER == "vllm" and bool(request.image)
    image_context = ""
    has_image = bool(request.image)
    has_file = bool(request.file)

    if request.image and not use_native_vllm_multimodal:
        image_context, _ = await _analyze_image_with_vision_service(
            image_data=request.image,
            user_message=request.message,
        )

    combined_context = _merge_context(image_context, rag_context, file_context)

    # Generate response (hybrid mode: use RAG when available, free chat otherwise)
    try:
        response_text = generate_response(
            question=request.message,
            context=combined_context,
            image_data=request.image if use_native_vllm_multimodal else None,
            image_format=image_format_to_store if use_native_vllm_multimodal else None,
            enable_thinking=effective_thinking,
            enable_tool_calling=effective_tool_calling,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

    reasoning_content, final_content = _split_reasoning_final_content(
        response_text,
        enable_thinking=effective_thinking,
    )
    display_content = final_content or response_text.strip() or response_text

    # Add assistant message to history
    add_message(
        session_id,
        "assistant",
        display_content,
        reasoning_content=reasoning_content,
        final_content=final_content or display_content,
    )

    return ChatResponse(
        content=display_content,
        session_id=session_id,
        sources=sources,
        metadata={
            "model": get_active_model_name(),
            "use_rag": bool(rag_context),
            "has_image": has_image,
            "has_file": has_file,
            "multimodal_mode": (
                "gemma4_native"
                if use_native_vllm_multimodal
                else ("vision_proxy" if request.image else ("text_with_file" if request.file else "text"))
            ),
            "deploy_profile": mode_config["deploy_profile"],
            "requested_deploy_profile": request.deploy_profile,
            "profile_source": mode_config.get("profile_source"),
            "enable_thinking": effective_thinking,
            "enable_tool_calling": effective_tool_calling,
            "requested_enable_thinking": request.enable_thinking,
            "requested_enable_tool_calling": request.enable_tool_calling,
            "mode_warnings": mode_warnings,
            "reasoning_content": reasoning_content,
            "final_content": final_content or display_content,
        },
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """Process a chat request with streaming response.

    Supports multimodal input when an image is provided in the request.

    Args:
        request: Chat request with message, optional image, and session info

    Returns:
        Streaming SSE response with generated tokens
    """
    # Trigger lazy loading if model not loaded
    if not is_model_loaded():
        try:
            get_llm()  # This will load the model
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Model loading failed: {str(e)}")

    _enforce_image_payload_limit(request.image)
    file_context, resolved_file_format = _build_file_context(
        file_data=request.file,
        file_name=request.file_name,
        file_format=request.file_format,
    )
    effective_thinking, effective_tool_calling, mode_warnings, mode_config = _resolve_mode_flags(request)

    # Create or use existing session
    session_id = request.session_id or create_session()

    use_native_vllm_multimodal = settings.LLM_PROVIDER == "vllm" and bool(request.image)
    image_context = ""
    has_image = bool(request.image)
    has_file = bool(request.file)
    image_format_to_store = _resolve_image_format(request.image, request.image_format)

    logger.info(
        "chat_stream request: session=%s msg_len=%d has_image=%s has_file=%s image_chars=%d file_chars=%d provider=%s native_vllm_mm=%s image_format=%s",
        session_id,
        len(request.message or ""),
        has_image,
        has_file,
        len(request.image or ""),
        len(request.file or ""),
        settings.LLM_PROVIDER,
        use_native_vllm_multimodal,
        image_format_to_store,
    )

    if request.image and not use_native_vllm_multimodal:
        logger.info("chat_stream using vision proxy path before LLM generation")
        image_context, _ = await _analyze_image_with_vision_service(
            image_data=request.image,
            user_message=request.message,
        )

    # Add user message to history (with image data)
    add_message(
        session_id,
        "user",
        request.message,
        has_image=bool(request.image),
        image_data=request.image,
        image_format=image_format_to_store,
        has_file=has_file,
        file_name=request.file_name,
        file_format=resolved_file_format,
    )

    rag_context, sources = _retrieve_rag_context(
        session_id=session_id,
        message=request.message,
        use_search=request.use_search,
    )
    combined_context = _merge_context(image_context, rag_context, file_context)

    async def event_generator():
        """Generate SSE events for streaming response."""
        try:
            # Send initial metadata
            yield {
                "event": "metadata",
                "data": json.dumps({
                    "session_id": session_id,
                    "sources": sources,
                    "has_context": bool(combined_context or use_native_vllm_multimodal),
                    "has_image": has_image,
                    "has_file": has_file,
                    "multimodal_mode": (
                        "gemma4_native"
                        if use_native_vllm_multimodal
                        else ("vision_proxy" if request.image else ("text_with_file" if request.file else "text"))
                    ),
                    "deploy_profile": mode_config["deploy_profile"],
                    "requested_deploy_profile": request.deploy_profile,
                    "profile_source": mode_config.get("profile_source"),
                    "enable_thinking": effective_thinking,
                    "enable_tool_calling": effective_tool_calling,
                    "requested_enable_thinking": request.enable_thinking,
                    "requested_enable_tool_calling": request.enable_tool_calling,
                    "mode_warnings": mode_warnings,
                }),
            }

            # Stream response (hybrid mode: use combined context when available)
            full_response = ""
            effective_question = request.message
            async for token in astream_response(
                question=effective_question,
                context=combined_context,
                image_data=request.image if use_native_vllm_multimodal else None,
                image_format=image_format_to_store if use_native_vllm_multimodal else None,
                enable_thinking=effective_thinking,
                enable_tool_calling=effective_tool_calling,
            ):
                full_response += token
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token}),
                }

            reasoning_content, final_content = _split_reasoning_final_content(
                full_response,
                enable_thinking=effective_thinking,
            )
            display_content = final_content or full_response.strip() or full_response

            # Send completion event
            yield {
                "event": "done",
                "data": json.dumps({
                    "session_id": session_id,
                    "full_content": full_response,
                    "reasoning_content": reasoning_content,
                    "final_content": final_content or display_content,
                    "display_content": display_content,
                }),
            }

            # Add to history after completion
            add_message(
                session_id,
                "assistant",
                display_content,
                reasoning_content=reasoning_content,
                final_content=final_content or display_content,
            )

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/history/{session_id}")
async def get_session_history(session_id: str):
    """Get conversation history for a session.

    Args:
        session_id: Session identifier

    Returns:
        Session history with all messages
    """
    session = get_session_info(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "title": session.get("title", "未命名对话"),
        "created": session.get("created", ""),
        "messages": session.get("messages", []),
        "message_count": len(session.get("messages", []))
    }


@router.delete("/history/{session_id}")
async def delete_session_history(session_id: str):
    """Delete a conversation session.

    Args:
        session_id: Session identifier

    Returns:
        Deletion confirmation
    """
    from app.services.session_service import delete_session

    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"deleted": True, "session_id": session_id}


@router.get("/sessions")
async def list_sessions():
    """Get all conversation sessions.

    Returns:
        List of all sessions with metadata
    """
    sessions = get_all_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session with full message history.

    Args:
        session_id: Session identifier

    Returns:
        Session with full message history
    """
    session = get_session_info(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.post("/sessions")
async def create_new_session(title: str = None):
    """Create a new conversation session.

    Args:
        title: Optional title for the session

    Returns:
        New session info
    """
    from fastapi import Query

    # Parse title from query or body
    session_id = create_session(title)
    return {
        "session_id": session_id,
        "title": title or "新对话",
        "message": "新会话已创建"
    }


@router.put("/sessions/{session_id}/title")
async def rename_session(session_id: str, request: SessionTitleRequest):
    """Update the title of a session.

    Args:
        session_id: Session identifier
        request: Request body with title

    Returns:
        Updated session info
    """
    updated = update_session_title(session_id, request.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"updated": True, "session_id": session_id, "title": request.title}


@router.delete("/sessions")
async def clear_all_session_history():
    """Clear all conversation sessions.

    Returns:
        Deletion confirmation with count
    """
    count = clear_all_sessions()
    return {"deleted": True, "count": count, "message": f"已清除 {count} 个会话"}
