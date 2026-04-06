"""Chat audio cache service.

Stores uploaded chat audio files on disk so chat requests can reference
local/internal audio URLs instead of external public links.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

_AUDIO_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_AUDIO_URL_PATH_PATTERN = re.compile(r"^/api/chat/audios/([a-f0-9]{32})/?$")
_DEFAULT_AUDIO_MIME = "audio/wav"
_EXT_MIME_MAP: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "flac": "audio/flac",
}
_MIME_EXT_MAP: dict[str, str] = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
    "audio/mp4": "m4a",
    "audio/flac": "flac",
}


def _cache_dir() -> Path:
    """Resolve and ensure chat audio cache directory."""
    configured = Path(settings.CHAT_AUDIO_CACHE_DIR)
    if not configured.is_absolute():
        configured = (BASE_DIR / configured).resolve()
    configured.mkdir(parents=True, exist_ok=True)
    return configured


def _allowed_extensions() -> set[str]:
    values: set[str] = set()
    for item in settings.CHAT_AUDIO_ALLOWED_EXTENSIONS.split(","):
        ext = item.strip().lower().lstrip(".")
        if ext:
            values.add(ext)
    return values


def _validate_audio_id(audio_id: str) -> str:
    normalized = (audio_id or "").strip().lower()
    if not _AUDIO_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="invalid audio_id")
    return normalized


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed to delete chat audio: %s", path, exc_info=True)


def _cleanup_cache() -> None:
    """Drop expired files and enforce cache max file count."""
    cache_dir = _cache_dir()
    now = time.time()
    ttl = settings.CHAT_AUDIO_CACHE_TTL_SECONDS

    files = sorted(
        (path for path in cache_dir.glob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    for path in files:
        age = now - path.stat().st_mtime
        if age > ttl:
            _remove_file(path)

    remaining = sorted(
        (path for path in cache_dir.glob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    overflow = len(remaining) - settings.CHAT_AUDIO_CACHE_MAX_FILES
    if overflow > 0:
        for path in remaining[:overflow]:
            _remove_file(path)


def _guess_extension(file_name: str | None, content_type: str | None) -> str:
    """Infer extension from file name / mime type."""
    allowed = _allowed_extensions()

    if file_name:
        ext = Path(file_name).suffix.lower().lstrip(".")
        if ext in allowed:
            return ext

    normalized_mime = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_mime in _MIME_EXT_MAP and _MIME_EXT_MAP[normalized_mime] in allowed:
        return _MIME_EXT_MAP[normalized_mime]

    guessed_ext = mimetypes.guess_extension(normalized_mime) if normalized_mime else None
    if guessed_ext:
        ext = guessed_ext.lstrip(".").lower()
        if ext == "oga":
            ext = "ogg"
        if ext in allowed:
            return ext

    # Conservative fallback to wav if allowed.
    if "wav" in allowed:
        return "wav"

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported audio format. Allowed: {', '.join(sorted(allowed))}",
    )


def _media_type_for_extension(extension: str) -> str:
    extension = extension.lower().lstrip(".")
    if extension in _EXT_MIME_MAP:
        return _EXT_MIME_MAP[extension]
    guessed, _ = mimetypes.guess_type(f"audio.{extension}")
    return guessed or _DEFAULT_AUDIO_MIME


def resolve_chat_audio_id_from_url(audio_url: str) -> str | None:
    """Resolve cached audio_id from local chat audio URL if matched."""
    raw = (audio_url or "").strip()
    if not raw:
        return None

    if raw.startswith("/"):
        path = raw
    else:
        from urllib.parse import urlparse
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return None
        path = parsed.path or ""

    matched = _AUDIO_URL_PATH_PATTERN.fullmatch(path)
    if not matched:
        return None
    return matched.group(1)


async def persist_uploaded_chat_audio(file: UploadFile) -> dict[str, int | str]:
    """Validate and cache uploaded chat audio file."""
    raw_bytes = await file.read()
    file_name = file.filename or ""
    content_type = file.content_type or ""
    await file.close()

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="audio file is empty")

    max_bytes = settings.MAX_CHAT_AUDIO_UPLOAD_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"audio file too large ({len(raw_bytes) / 1024 / 1024:.2f}MB), "
                f"limit {settings.MAX_CHAT_AUDIO_UPLOAD_MB}MB"
            ),
        )

    extension = _guess_extension(file_name=file_name, content_type=content_type)
    media_type = _media_type_for_extension(extension)
    audio_id = uuid.uuid4().hex
    path = _cache_dir() / f"{audio_id}.{extension}"
    path.write_bytes(raw_bytes)
    _cleanup_cache()
    return {
        "audio_id": audio_id,
        "audio_format": extension,
        "media_type": media_type,
        "size_bytes": len(raw_bytes),
        "file_name": file_name,
        "expires_in_seconds": settings.CHAT_AUDIO_CACHE_TTL_SECONDS,
    }


def get_chat_audio_file(audio_id: str) -> tuple[Path, str]:
    """Resolve cached audio path by audio_id."""
    normalized_id = _validate_audio_id(audio_id)
    matches = sorted(_cache_dir().glob(f"{normalized_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="audio not found or expired")

    path = matches[0]
    age = time.time() - path.stat().st_mtime
    if age > settings.CHAT_AUDIO_CACHE_TTL_SECONDS:
        _remove_file(path)
        raise HTTPException(status_code=404, detail="audio not found or expired")

    extension = path.suffix.lstrip(".")
    return path, _media_type_for_extension(extension)


def resolve_chat_audio_data_url(audio_id: str) -> str:
    """Read cached audio and convert to data URL for vLLM audio block."""
    audio_path, media_type = get_chat_audio_file(audio_id)
    encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
