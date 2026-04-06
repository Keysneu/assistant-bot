"""Chat API endpoints.

Handles streaming and non-streaming chat responses with RAG support.
Supports Gemma4 native multimodal input (image/audio/video) on vLLM.
"""
import base64
import json
import re
import logging
import mimetypes
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from pypdf import PdfReader
import httpx

from app.core.config import settings
from app.models.schema import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    SessionTitleRequest,
    ChatModeConfigResponse,
    ChatImageUploadResponse,
    ChatAudioUploadResponse,
    ChatVideoUploadResponse,
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
from app.services.chat_image_service import (
    persist_uploaded_chat_image,
    get_chat_image_file,
    resolve_chat_image_payload,
    persist_chat_image_from_base64,
)
from app.services.chat_audio_service import (
    persist_uploaded_chat_audio,
    get_chat_audio_file,
    resolve_chat_audio_id_from_url,
    resolve_chat_audio_data_url,
)
from app.services.chat_video_service import (
    persist_uploaded_chat_video,
    get_chat_video_file,
    resolve_chat_video_id_from_url,
    resolve_chat_video_data_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

VLLM_PROFILE_CAPABILITIES: dict[str, dict[str, bool]] = {
    "rag_text": {
        "supports_image": False,
        "supports_audio": False,
        "supports_video": False,
        "supports_thinking": True,
        "supports_tool_calling": False,
    },
    "vision": {
        "supports_image": True,
        "supports_audio": False,
        "supports_video": False,
        "supports_thinking": True,
        "supports_tool_calling": False,
    },
    "full": {
        "supports_image": True,
        "supports_audio": True,
        "supports_video": True,
        "supports_thinking": True,
        "supports_tool_calling": True,
    },
    "full_featured": {
        "supports_image": True,
        "supports_audio": True,
        "supports_video": True,
        "supports_thinking": True,
        "supports_tool_calling": True,
    },
    "benchmark": {
        "supports_image": False,
        "supports_audio": False,
        "supports_video": False,
        "supports_thinking": False,
        "supports_tool_calling": False,
    },
    "extreme": {
        "supports_image": False,
        "supports_audio": False,
        "supports_video": False,
        "supports_thinking": False,
        "supports_tool_calling": False,
    },
}

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


def _resolve_effective_profile(request_profile: str | None = None) -> tuple[str, str, list[str]]:
    """Resolve effective profile and source for this request.

    Runtime/request profile switching is intentionally disabled.
    Effective profile is locked to backend env setting.
    """
    if settings.LLM_PROVIDER != "vllm":
        return "local_default", "local_default", []

    env_profile = _normalize_profile(settings.VLLM_DEPLOY_PROFILE)
    if env_profile:
        warnings: list[str] = []
        if request_profile:
            warnings.append(
                f"Requested profile '{request_profile}' ignored; server is locked to '{env_profile}'"
            )
        return env_profile, "env_locked", warnings

    return "full_featured", "fallback_full_featured", []


def _current_mode_config(request_profile: str | None = None) -> dict[str, object]:
    """Resolve runtime mode capability based on provider + effective profile."""
    if settings.LLM_PROVIDER != "vllm":
        return {
            "provider": settings.LLM_PROVIDER,
            "deploy_profile": "local_default",
            "supports_image": True,
            "supports_audio": False,
            "supports_video": False,
            "supports_thinking": False,
            "supports_tool_calling": False,
            "available_profiles": [],
            "configured_profile": None,
            "runtime_profile_override": None,
            "profile_source": "local_default",
        }

    effective_profile, profile_source, _ = _resolve_effective_profile(request_profile)
    caps = VLLM_PROFILE_CAPABILITIES[effective_profile]
    return {
        "provider": settings.LLM_PROVIDER,
        "deploy_profile": effective_profile,
        **caps,
        "available_profiles": [],
        "configured_profile": settings.VLLM_DEPLOY_PROFILE,
        "runtime_profile_override": None,
        "profile_source": profile_source,
    }


def _resolve_mode_flags(request: ChatRequest) -> tuple[bool, bool, list[str], dict[str, object]]:
    """Resolve effective thinking/tool flags under current deploy profile."""
    mode_config = _current_mode_config(request.deploy_profile)
    supports_thinking = bool(mode_config.get("supports_thinking", False))
    supports_tool_calling = bool(mode_config.get("supports_tool_calling", False))

    _, _, profile_warnings = _resolve_effective_profile(request.deploy_profile)
    warnings: list[str] = [str(item) for item in profile_warnings if str(item).strip()]

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

    has_image_input = bool(
        (request.image and request.image.strip())
        or (request.image_id and request.image_id.strip())
        or (request.images and any(item and item.strip() for item in request.images))
        or (request.image_ids and any(item and item.strip() for item in request.image_ids))
    )
    has_audio_input = bool(
        (request.audio_url and request.audio_url.strip())
        or (request.audio_urls and any(item and item.strip() for item in request.audio_urls))
    )
    has_video_input = bool(
        (request.video_url and request.video_url.strip())
        or (request.video_urls and any(item and item.strip() for item in request.video_urls))
    )
    if has_image_input and settings.LLM_PROVIDER == "vllm" and not bool(mode_config.get("supports_image", False)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Current deploy profile '{mode_config['deploy_profile']}' does not support image mode. "
                "Please use a server startup profile that supports images (recommended: full_featured)."
            ),
        )
    if has_audio_input and settings.LLM_PROVIDER != "vllm":
        raise HTTPException(
            status_code=400,
            detail=(
                "Audio input currently requires LLM_PROVIDER=vllm. "
                "Please switch to vLLM (Gemma4 E2B/E4B with audio support)."
            ),
        )
    if has_audio_input and settings.LLM_PROVIDER == "vllm" and not bool(mode_config.get("supports_audio", False)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Current deploy profile '{mode_config['deploy_profile']}' does not support audio mode. "
                "Please use a server startup profile that supports audio (recommended: full/full_featured)."
            ),
        )
    if has_video_input and settings.LLM_PROVIDER != "vllm":
        raise HTTPException(
            status_code=400,
            detail=(
                "Video input currently requires LLM_PROVIDER=vllm. "
                "Please switch to vLLM (Gemma4 E2B/E4B with video support)."
            ),
        )
    if has_video_input and settings.LLM_PROVIDER == "vllm" and not bool(mode_config.get("supports_video", False)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Current deploy profile '{mode_config['deploy_profile']}' does not support video mode. "
                "Please use a server startup profile that supports videos (recommended: full/full_featured)."
            ),
        )

    return effective_thinking, effective_tool_calling, warnings, mode_config


def _resolve_generation_overrides(request: ChatRequest) -> tuple[int, float, float]:
    """Resolve effective generation params for metadata/debug visibility."""
    effective_max_tokens = request.max_tokens if request.max_tokens is not None else settings.MAX_TOKENS
    effective_max_tokens = max(1, min(int(effective_max_tokens), settings.MAX_TOKENS_HARD_LIMIT))
    effective_temperature = settings.TEMPERATURE if request.temperature is None else float(request.temperature)
    effective_top_p = settings.TOP_P if request.top_p is None else float(request.top_p)
    return effective_max_tokens, effective_temperature, effective_top_p


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


def _normalize_str_list(values: list[str] | None, lower: bool = False) -> list[str]:
    """Normalize optional string list by trimming empties."""
    normalized: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        normalized.append(text.lower() if lower else text)
    return normalized


def _resolve_image_inputs(request: ChatRequest) -> tuple[list[str], list[str | None], list[str]]:
    """Resolve single/multi image inputs into normalized payloads + formats + cached IDs."""
    payloads: list[str] = []
    formats: list[str | None] = []
    cached_ids: list[str] = []

    inline_payloads, inline_formats = _resolve_inline_image_inputs(request)
    payloads.extend(inline_payloads)
    formats.extend(inline_formats)

    if request.image_id:
        payload, payload_format = resolve_chat_image_payload(image_data=None, image_id=request.image_id)
        _enforce_image_payload_limit(payload)
        payloads.append(payload or "")
        formats.append(payload_format or request.image_format or "jpeg")
        cached_ids.append(request.image_id.strip().lower())

    for image_id in _normalize_str_list(request.image_ids, lower=True):
        payload, payload_format = resolve_chat_image_payload(image_data=None, image_id=image_id)
        _enforce_image_payload_limit(payload)
        payloads.append(payload or "")
        formats.append(payload_format or "jpeg")
        cached_ids.append(image_id)

    return payloads, formats, cached_ids


def _validate_audio_url(audio_url: str) -> str:
    """Validate supported audio URL formats for Gemma4 multimodal input."""
    normalized = audio_url.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="audio_url cannot be empty")

    if normalized.startswith("data:audio/"):
        return normalized

    local_audio_id = resolve_chat_audio_id_from_url(normalized)
    if local_audio_id:
        return normalized

    parsed = urlparse(normalized)
    if settings.ALLOW_PUBLIC_AUDIO_URLS and parsed.scheme in {"http", "https"} and parsed.netloc:
        return normalized

    raise HTTPException(
        status_code=400,
        detail=(
            "audio_url only supports local uploaded audio URLs "
            "('/api/chat/audios/{audio_id}' or full URL with same path) "
            "or data:audio/* data URL. Public internet audio URLs are disabled."
        ),
    )


def _resolve_audio_inputs(request: ChatRequest) -> list[str]:
    """Resolve single/multi audio URL inputs into a normalized list."""
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in [request.audio_url, *(request.audio_urls or [])]:
        if not raw:
            continue
        normalized = _validate_audio_url(str(raw))
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


def _is_data_audio_url(audio_url: str) -> bool:
    """Check whether URL is already an inline audio data URL."""
    return audio_url.startswith("data:audio/")


def _infer_audio_mime_type(audio_url: str, content_type: str | None) -> str:
    """Infer best-effort audio MIME type from response header or URL suffix."""
    candidate = (content_type or "").split(";", 1)[0].strip().lower()
    if candidate.startswith("audio/"):
        return candidate

    path = urlparse(audio_url).path
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith("audio/"):
        return guessed

    return "audio/wav"


async def _fetch_audio_url_as_data_url(audio_url: str) -> str:
    """Resolve audio URL to data URL for vLLM audio blocks."""
    if _is_data_audio_url(audio_url):
        return audio_url

    local_audio_id = resolve_chat_audio_id_from_url(audio_url)
    if local_audio_id:
        return resolve_chat_audio_data_url(local_audio_id)

    parsed = urlparse(audio_url)
    if parsed.scheme not in {"http", "https"}:
        return audio_url

    timeout = httpx.Timeout(
        timeout=settings.AUDIO_FETCH_TIMEOUT_SECONDS,
        connect=min(10.0, settings.AUDIO_FETCH_TIMEOUT_SECONDS),
    )
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            response = await client.get(audio_url)
            response.raise_for_status()
            audio_bytes = response.content
            if not audio_bytes:
                raise ValueError("empty audio payload")
            if len(audio_bytes) > settings.MAX_AUDIO_FETCH_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Audio payload too large ({len(audio_bytes)} bytes). "
                        f"Limit is {settings.MAX_AUDIO_FETCH_BYTES} bytes."
                    ),
                )
            mime_type = _infer_audio_mime_type(
                audio_url=audio_url,
                content_type=response.headers.get("content-type"),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise RuntimeError(f"prefetch audio failed for '{audio_url}': {exc}") from exc

    encoded = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _prepare_audio_urls_for_vllm(audio_urls: list[str]) -> tuple[list[str], list[str]]:
    """Convert remote audio URLs to data URLs; fallback to original URL if prefetch fails."""
    prepared: list[str] = []
    warnings: list[str] = []

    for url in audio_urls:
        try:
            prepared.append(await _fetch_audio_url_as_data_url(url))
        except HTTPException:
            raise
        except Exception as exc:
            warnings.append(str(exc))
            prepared.append(url)

    return prepared, warnings


def _validate_video_url(video_url: str) -> str:
    """Validate supported video URL formats for Gemma4 multimodal input."""
    normalized = video_url.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="video_url cannot be empty")

    if normalized.startswith("data:video/"):
        return normalized

    local_video_id = resolve_chat_video_id_from_url(normalized)
    if local_video_id:
        return normalized

    parsed = urlparse(normalized)
    if settings.ALLOW_PUBLIC_VIDEO_URLS and parsed.scheme in {"http", "https"} and parsed.netloc:
        return normalized

    raise HTTPException(
        status_code=400,
        detail=(
            "video_url only supports local uploaded video URLs "
            "('/api/chat/videos/{video_id}' or full URL with same path) "
            "or data:video/* data URL. Public internet video URLs are disabled."
        ),
    )


def _resolve_video_inputs(request: ChatRequest) -> list[str]:
    """Resolve single/multi video URL inputs into a normalized list."""
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in [request.video_url, *(request.video_urls or [])]:
        if not raw:
            continue
        normalized = _validate_video_url(str(raw))
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


def _prepare_video_url_for_vllm(video_url: str) -> str:
    """Prepare video transport payload for vLLM (data_url preferred for local uploads)."""
    if video_url.startswith("data:video/"):
        return video_url

    local_video_id = resolve_chat_video_id_from_url(video_url)
    if local_video_id:
        if settings.LOCAL_VIDEO_TRANSPORT_MODE == "data_url":
            return resolve_chat_video_data_url(local_video_id)
        if video_url.startswith("/"):
            return f"{settings.LOCAL_MEDIA_BASE_URL.rstrip('/')}{video_url}"
        return video_url

    return video_url


def _prepare_video_urls_for_vllm(video_urls: list[str]) -> tuple[list[str], list[str]]:
    """Normalize video URLs for vLLM payload (local path -> absolute URL)."""
    prepared: list[str] = []
    warnings: list[str] = []

    for url in video_urls:
        try:
            prepared.append(_prepare_video_url_for_vllm(url))
        except HTTPException:
            raise
        except Exception as exc:
            warnings.append(str(exc))
            prepared.append(url)

    return prepared, warnings


def _resolve_inline_image_inputs(request: ChatRequest) -> tuple[list[str], list[str | None]]:
    """Resolve inline image payloads from request (single + multiple)."""
    payloads: list[str] = []
    formats: list[str | None] = []

    if request.image:
        _enforce_image_payload_limit(request.image)
        payloads.append(request.image)
        formats.append(_resolve_image_format(request.image, request.image_format))

    inline_images = _normalize_str_list(request.images)
    inline_formats = _normalize_str_list(request.image_formats, lower=True)
    for idx, image_data in enumerate(inline_images):
        _enforce_image_payload_limit(image_data)
        format_hint = inline_formats[idx] if idx < len(inline_formats) else request.image_format
        payloads.append(image_data)
        formats.append(_resolve_image_format(image_data, format_hint))

    return payloads, formats


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


async def _analyze_images_with_vision_service(
    image_payloads: list[str],
    user_message: str,
) -> str:
    """Analyze multiple images with legacy vision proxy path and merge contexts."""
    contexts: list[str] = []
    for idx, payload in enumerate(image_payloads):
        image_context, analyzed = await _analyze_image_with_vision_service(
            image_data=payload,
            user_message=user_message,
        )
        if not analyzed or not image_context:
            continue
        if len(image_payloads) > 1:
            contexts.append(f"【图片 {idx + 1} 分析】\n{image_context}")
        else:
            contexts.append(image_context)
    return "\n\n".join(contexts)


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


def _resolve_multimodal_mode(
    *,
    native_vllm_multimodal: bool,
    has_image: bool,
    has_audio: bool,
    has_video: bool,
    has_file: bool,
) -> str:
    """Resolve multimodal mode label for response metadata."""
    if native_vllm_multimodal:
        if has_image and has_audio and has_video:
            return "gemma4_native_image_video_audio"
        if has_image and has_video:
            return "gemma4_native_image_video"
        if has_image and has_audio:
            return "gemma4_native_image_audio"
        if has_video and has_audio:
            return "gemma4_native_video_audio"
        if has_image:
            return "gemma4_native_image"
        if has_video:
            return "gemma4_native_video"
        if has_audio:
            return "gemma4_native_audio"
    if has_image:
        return "vision_proxy"
    if has_file:
        return "text_with_file"
    return "text"


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


@router.post("/images/upload", response_model=ChatImageUploadResponse)
async def upload_chat_image(file: UploadFile = File(...)) -> ChatImageUploadResponse:
    """Upload a chat image and return lightweight image_id reference."""
    payload = await persist_uploaded_chat_image(file)
    return ChatImageUploadResponse(**payload)


@router.get("/images/{image_id}")
async def get_chat_image(image_id: str):
    """Fetch cached chat image by image_id for session history rendering."""
    image_path, media_type = get_chat_image_file(image_id)
    return FileResponse(
        image_path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/audios/upload", response_model=ChatAudioUploadResponse)
async def upload_chat_audio(file: UploadFile = File(...)) -> ChatAudioUploadResponse:
    """Upload a chat audio file and return lightweight audio_id reference."""
    payload = await persist_uploaded_chat_audio(file)
    return ChatAudioUploadResponse(**payload)


@router.get("/audios/{audio_id}")
async def get_chat_audio(audio_id: str):
    """Fetch cached chat audio by audio_id for session history rendering."""
    audio_path, media_type = get_chat_audio_file(audio_id)
    return FileResponse(
        audio_path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/videos/upload", response_model=ChatVideoUploadResponse)
async def upload_chat_video(file: UploadFile = File(...)) -> ChatVideoUploadResponse:
    """Upload a chat video file and return lightweight video_id reference."""
    payload = await persist_uploaded_chat_video(file)
    return ChatVideoUploadResponse(**payload)


@router.get("/videos/{video_id}")
async def get_chat_video(video_id: str):
    """Fetch cached chat video by video_id for session history rendering."""
    video_path, media_type = get_chat_video_file(video_id)
    return FileResponse(
        video_path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


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

    resolved_image_payloads, resolved_image_formats, requested_cached_image_ids = _resolve_image_inputs(request)
    resolved_audio_urls = _resolve_audio_inputs(request)
    resolved_video_urls = _resolve_video_inputs(request)
    inline_image_payloads, inline_image_formats = _resolve_inline_image_inputs(request)
    file_context, resolved_file_format = _build_file_context(
        file_data=request.file,
        file_name=request.file_name,
        file_format=request.file_format,
    )
    effective_thinking, effective_tool_calling, mode_warnings, mode_config = _resolve_mode_flags(request)
    effective_max_tokens, effective_temperature, effective_top_p = _resolve_generation_overrides(request)
    vllm_audio_urls = list(resolved_audio_urls)
    vllm_video_urls = list(resolved_video_urls)
    audio_prefetch_warnings: list[str] = []
    if settings.LLM_PROVIDER == "vllm" and resolved_audio_urls:
        vllm_audio_urls, audio_prefetch_warnings = await _prepare_audio_urls_for_vllm(resolved_audio_urls)
        mode_warnings.extend(audio_prefetch_warnings)
    video_prepare_warnings: list[str] = []
    if settings.LLM_PROVIDER == "vllm" and resolved_video_urls:
        vllm_video_urls, video_prepare_warnings = _prepare_video_urls_for_vllm(resolved_video_urls)
        mode_warnings.extend(video_prepare_warnings)

    # Create or use existing session
    session_id = request.session_id or create_session()

    cached_image_ids = list(requested_cached_image_ids)
    session_image_data: str | None = None
    for idx, inline_image in enumerate(inline_image_payloads):
        try:
            cached = persist_chat_image_from_base64(inline_image)
            cached_image_ids.append(str(cached["image_id"]))
            resolved_image_formats[idx] = str(cached.get("image_format") or resolved_image_formats[idx] or "jpeg")
        except HTTPException as cache_error:
            logger.warning("Persist inline image failed: %s", cache_error.detail)
            if not session_image_data and len(_extract_base64_payload(inline_image)) <= settings.MAX_SESSION_IMAGE_BASE64_CHARS:
                session_image_data = inline_image

    primary_image_id = cached_image_ids[0] if cached_image_ids else None
    primary_image_format = resolved_image_formats[0] if resolved_image_formats else None
    image_format_to_store = (
        primary_image_format
        or (inline_image_formats[0] if inline_image_formats else None)
        or request.image_format
    )
    add_message(
        session_id,
        "user",
        request.message,
        has_image=bool(resolved_image_payloads),
        image_data=session_image_data,
        image_format=image_format_to_store,
        image_id=primary_image_id,
        image_ids=cached_image_ids or None,
        has_file=bool(request.file),
        file_name=request.file_name,
        file_format=resolved_file_format,
        has_audio=bool(resolved_audio_urls),
        audio_url=resolved_audio_urls[0] if resolved_audio_urls else None,
        audio_urls=resolved_audio_urls or None,
        has_video=bool(resolved_video_urls),
        video_url=resolved_video_urls[0] if resolved_video_urls else None,
        video_urls=resolved_video_urls or None,
    )

    rag_context, sources = _retrieve_rag_context(
        session_id=session_id,
        message=request.message,
        use_search=request.use_search,
    )

    use_native_vllm_multimodal = settings.LLM_PROVIDER == "vllm" and bool(
        resolved_image_payloads or resolved_audio_urls or resolved_video_urls
    )
    use_native_vllm_image = settings.LLM_PROVIDER == "vllm" and bool(resolved_image_payloads)
    image_context = ""
    has_image = bool(resolved_image_payloads)
    has_file = bool(request.file)
    has_audio = bool(resolved_audio_urls)
    has_video = bool(resolved_video_urls)
    audio_prefetched_count = sum(
        1 for raw, prepared in zip(resolved_audio_urls, vllm_audio_urls) if raw != prepared
    )

    if resolved_image_payloads and not use_native_vllm_image:
        image_context = await _analyze_images_with_vision_service(
            image_payloads=resolved_image_payloads,
            user_message=request.message,
        )

    combined_context = _merge_context(image_context, rag_context, file_context)

    # Generate response (hybrid mode: use RAG when available, free chat otherwise)
    try:
        response_text = generate_response(
            question=request.message,
            context=combined_context,
            image_data=resolved_image_payloads[0] if use_native_vllm_multimodal and resolved_image_payloads else None,
            image_format=resolved_image_formats[0] if use_native_vllm_multimodal and resolved_image_formats else None,
            image_data_list=(
                resolved_image_payloads[1:]
                if use_native_vllm_image and len(resolved_image_payloads) > 1
                else None
            ),
            image_format_list=(
                resolved_image_formats[1:]
                if use_native_vllm_image and len(resolved_image_formats) > 1
                else None
            ),
            audio_url=vllm_audio_urls[0] if use_native_vllm_multimodal and vllm_audio_urls else None,
            audio_url_list=(
                vllm_audio_urls[1:]
                if use_native_vllm_multimodal and len(vllm_audio_urls) > 1
                else None
            ),
            video_url=vllm_video_urls[0] if use_native_vllm_multimodal and vllm_video_urls else None,
            video_url_list=(
                vllm_video_urls[1:]
                if use_native_vllm_multimodal and len(vllm_video_urls) > 1
                else None
            ),
            enable_thinking=effective_thinking,
            enable_tool_calling=effective_tool_calling,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
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
            "has_audio": has_audio,
            "has_video": has_video,
            "has_file": has_file,
            "multimodal_mode": _resolve_multimodal_mode(
                native_vllm_multimodal=use_native_vllm_multimodal,
                has_image=has_image,
                has_audio=has_audio,
                has_video=has_video,
                has_file=has_file,
            ),
            "image_id": primary_image_id,
            "image_ids": cached_image_ids,
            "image_count": len(resolved_image_payloads),
            "audio_url": resolved_audio_urls[0] if resolved_audio_urls else None,
            "audio_urls": resolved_audio_urls,
            "audio_count": len(resolved_audio_urls),
            "audio_prefetched_count": audio_prefetched_count,
            "video_url": resolved_video_urls[0] if resolved_video_urls else None,
            "video_urls": resolved_video_urls,
            "video_count": len(resolved_video_urls),
            "deploy_profile": mode_config["deploy_profile"],
            "requested_deploy_profile": request.deploy_profile,
            "profile_source": mode_config.get("profile_source"),
            "enable_thinking": effective_thinking,
            "enable_tool_calling": effective_tool_calling,
            "requested_enable_thinking": request.enable_thinking,
            "requested_enable_tool_calling": request.enable_tool_calling,
            "mode_warnings": mode_warnings,
            "requested_max_tokens": request.max_tokens,
            "effective_max_tokens": effective_max_tokens,
            "effective_temperature": effective_temperature,
            "effective_top_p": effective_top_p,
            "reasoning_content": reasoning_content,
            "final_content": final_content or display_content,
        },
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """Process a chat request with streaming response.

    Supports multimodal input when image/audio/video is provided in the request.

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

    resolved_image_payloads, resolved_image_formats, requested_cached_image_ids = _resolve_image_inputs(request)
    resolved_audio_urls = _resolve_audio_inputs(request)
    resolved_video_urls = _resolve_video_inputs(request)
    inline_image_payloads, inline_image_formats = _resolve_inline_image_inputs(request)
    file_context, resolved_file_format = _build_file_context(
        file_data=request.file,
        file_name=request.file_name,
        file_format=request.file_format,
    )
    effective_thinking, effective_tool_calling, mode_warnings, mode_config = _resolve_mode_flags(request)
    effective_max_tokens, effective_temperature, effective_top_p = _resolve_generation_overrides(request)
    vllm_audio_urls = list(resolved_audio_urls)
    vllm_video_urls = list(resolved_video_urls)
    audio_prefetch_warnings: list[str] = []
    if settings.LLM_PROVIDER == "vllm" and resolved_audio_urls:
        vllm_audio_urls, audio_prefetch_warnings = await _prepare_audio_urls_for_vllm(resolved_audio_urls)
        mode_warnings.extend(audio_prefetch_warnings)
    video_prepare_warnings: list[str] = []
    if settings.LLM_PROVIDER == "vllm" and resolved_video_urls:
        vllm_video_urls, video_prepare_warnings = _prepare_video_urls_for_vllm(resolved_video_urls)
        mode_warnings.extend(video_prepare_warnings)

    # Create or use existing session
    session_id = request.session_id or create_session()

    cached_image_ids = list(requested_cached_image_ids)
    session_image_data: str | None = None
    for idx, inline_image in enumerate(inline_image_payloads):
        try:
            cached = persist_chat_image_from_base64(inline_image)
            cached_image_ids.append(str(cached["image_id"]))
            resolved_image_formats[idx] = str(cached.get("image_format") or resolved_image_formats[idx] or "jpeg")
        except HTTPException as cache_error:
            logger.warning("Persist inline image failed: %s", cache_error.detail)
            if not session_image_data and len(_extract_base64_payload(inline_image)) <= settings.MAX_SESSION_IMAGE_BASE64_CHARS:
                session_image_data = inline_image

    use_native_vllm_multimodal = settings.LLM_PROVIDER == "vllm" and bool(
        resolved_image_payloads or resolved_audio_urls or resolved_video_urls
    )
    use_native_vllm_image = settings.LLM_PROVIDER == "vllm" and bool(resolved_image_payloads)
    image_context = ""
    has_image = bool(resolved_image_payloads)
    has_audio = bool(resolved_audio_urls)
    has_video = bool(resolved_video_urls)
    has_file = bool(request.file)
    audio_prefetched_count = sum(
        1 for raw, prepared in zip(resolved_audio_urls, vllm_audio_urls) if raw != prepared
    )
    primary_image_id = cached_image_ids[0] if cached_image_ids else None
    primary_image_format = resolved_image_formats[0] if resolved_image_formats else None
    image_format_to_store = (
        primary_image_format
        or (inline_image_formats[0] if inline_image_formats else None)
        or request.image_format
    )

    logger.info(
        "chat_stream request: session=%s msg_len=%d image_count=%d audio_count=%d video_count=%d has_file=%s image_chars=%d file_chars=%d provider=%s native_vllm_mm=%s image_format=%s",
        session_id,
        len(request.message or ""),
        len(resolved_image_payloads),
        len(vllm_audio_urls),
        len(vllm_video_urls),
        has_file,
        sum(len(item or "") for item in resolved_image_payloads),
        len(request.file or ""),
        settings.LLM_PROVIDER,
        use_native_vllm_multimodal,
        image_format_to_store,
    )

    if resolved_image_payloads and not use_native_vllm_image:
        logger.info("chat_stream using vision proxy path before LLM generation")
        image_context = await _analyze_images_with_vision_service(
            image_payloads=resolved_image_payloads,
            user_message=request.message,
        )

    # Add user message to history (with image data)
    add_message(
        session_id,
        "user",
        request.message,
        has_image=bool(resolved_image_payloads),
        image_data=session_image_data,
        image_format=image_format_to_store,
        image_id=primary_image_id,
        image_ids=cached_image_ids or None,
        has_file=has_file,
        file_name=request.file_name,
        file_format=resolved_file_format,
        has_audio=has_audio,
        audio_url=resolved_audio_urls[0] if resolved_audio_urls else None,
        audio_urls=resolved_audio_urls or None,
        has_video=has_video,
        video_url=resolved_video_urls[0] if resolved_video_urls else None,
        video_urls=resolved_video_urls or None,
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
                    "has_audio": has_audio,
                    "has_video": has_video,
                    "has_file": has_file,
                    "multimodal_mode": _resolve_multimodal_mode(
                        native_vllm_multimodal=use_native_vllm_multimodal,
                        has_image=has_image,
                        has_audio=has_audio,
                        has_video=has_video,
                        has_file=has_file,
                    ),
                    "image_id": primary_image_id,
                    "image_ids": cached_image_ids,
                    "image_count": len(resolved_image_payloads),
                    "audio_url": resolved_audio_urls[0] if resolved_audio_urls else None,
                    "audio_urls": resolved_audio_urls,
                    "audio_count": len(resolved_audio_urls),
                    "audio_prefetched_count": audio_prefetched_count,
                    "video_url": resolved_video_urls[0] if resolved_video_urls else None,
                    "video_urls": resolved_video_urls,
                    "video_count": len(resolved_video_urls),
                    "deploy_profile": mode_config["deploy_profile"],
                    "requested_deploy_profile": request.deploy_profile,
                    "profile_source": mode_config.get("profile_source"),
                    "enable_thinking": effective_thinking,
                    "enable_tool_calling": effective_tool_calling,
                    "requested_enable_thinking": request.enable_thinking,
                    "requested_enable_tool_calling": request.enable_tool_calling,
                    "mode_warnings": mode_warnings,
                    "requested_max_tokens": request.max_tokens,
                    "effective_max_tokens": effective_max_tokens,
                    "effective_temperature": effective_temperature,
                    "effective_top_p": effective_top_p,
                }),
            }

            # Stream response (hybrid mode: use combined context when available)
            full_response = ""
            effective_question = request.message
            async for token in astream_response(
                question=effective_question,
                context=combined_context,
                image_data=(
                    resolved_image_payloads[0]
                    if use_native_vllm_image and resolved_image_payloads
                    else None
                ),
                image_format=(
                    resolved_image_formats[0]
                    if use_native_vllm_image and resolved_image_formats
                    else None
                ),
                image_data_list=(
                    resolved_image_payloads[1:]
                    if use_native_vllm_image and len(resolved_image_payloads) > 1
                    else None
                ),
                image_format_list=(
                    resolved_image_formats[1:]
                    if use_native_vllm_image and len(resolved_image_formats) > 1
                    else None
                ),
                audio_url=vllm_audio_urls[0] if use_native_vllm_multimodal and vllm_audio_urls else None,
                audio_url_list=(
                    vllm_audio_urls[1:]
                    if use_native_vllm_multimodal and len(vllm_audio_urls) > 1
                    else None
                ),
                video_url=vllm_video_urls[0] if use_native_vllm_multimodal and vllm_video_urls else None,
                video_url_list=(
                    vllm_video_urls[1:]
                    if use_native_vllm_multimodal and len(vllm_video_urls) > 1
                    else None
                ),
                enable_thinking=effective_thinking,
                enable_tool_calling=effective_tool_calling,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
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
