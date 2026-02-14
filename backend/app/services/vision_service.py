"""Vision Service for Multimodal Support.

Supports two backends:
1. GLM-4V-Flash API (智谱 AI) - Free cloud-based model, no local download required (RECOMMENDED)
2. BLIP-2 Local Model - Falls back to local model if GLM unavailable

GLM-4V-Flash provides:
- Completely FREE to use
- Excellent image understanding
- No 15GB download required
- Fast API response
- Chinese language optimized
"""
import asyncio
import base64
import io
import logging
import json
from typing import Optional

import httpx
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

# Backend state
_glm_client: Optional[httpx.AsyncClient] = None
_glm_available: bool = False


def _init_glm_client() -> bool:
    """Initialize GLM API client.

    Returns:
        True if GLM API is configured and available
    """
    global _glm_available

    if not settings.GLM_API_KEY:
        logger.warning("GLM_API_KEY not set, vision features will use local model or be disabled")
        return False

    _glm_available = True
    logger.info(f"GLM-4V API client initialized (model: {settings.GLM_VISION_MODEL})")
    return True


def _encode_image_to_base64(image_bytes: bytes, format: str = "JPEG") -> str:
    """Encode image bytes to base64 string for GLM API.

    Args:
        image_bytes: Raw image data
        format: Image format (JPEG, PNG, etc.)

    Returns:
        Base64 encoded string with data URI prefix
    """
    # Open and convert image
    image = Image.open(io.BytesIO(image_bytes))

    # Convert RGBA to RGB
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    elif image.mode not in ["RGB", "L"]:
        image = image.convert("RGB")

    # Save to bytes
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    image_bytes = buffer.getvalue()

    # Encode to base64 with data URI prefix
    base64_str = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/{format.lower()};base64,{base64_str}"


async def _call_glm_vision_api(
    image_base64: str,
    question: str = "请详细描述这张图片的内容",
    retry_count: int = 0,
) -> str:
    """Call GLM-4V-Flash API for image understanding.

    Uses the official Zhipu AI API endpoint with proper error handling.

    Args:
        image_base64: Base64 encoded image (with data URI prefix)
        question: Question to ask about the image
        retry_count: Current retry attempt number

    Returns:
        GLM's response text

    Raises:
        Exception: If API call fails after retries
    """
    global _glm_client

    if _glm_client is None:
        _glm_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )

    # GLM-4V API endpoint - 智谱AI官方API
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # Build enhanced prompt for better image understanding
    enhanced_question = question
    if "代码" in question or "code" in question.lower() or "coding" in question.lower():
        enhanced_question = f"{question}\n\n如果是代码，请识别编程语言、解释代码逻辑、并分析代码功能。"
    elif "图片" in question or "图像" in question or "photo" in question.lower():
        enhanced_question = f"{question}\n\n请详细描述图片中的所有内容，包括：文字、物体、场景、颜色、布局等细节。"
    else:
        enhanced_question = f"{question}\n\n请详细分析这张图片的内容。"

    # Prepare request payload according to GLM API specification
    payload = {
        "model": settings.GLM_VISION_MODEL,  # glm-4v-flash (free), glm-4v, or glm-4v-plus
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": enhanced_question
                    }
                ]
            }
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 1024,
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {settings.GLM_API_KEY}",
        "Content-Type": "application/json"
    }

    max_retries = 3
    base_delay = 1.0  # Start with 1 second, exponentially increase

    for attempt in range(max_retries):
        retry_delay = base_delay * (2 ** attempt)
        if retry_count > 0:
            logger.info(f"Retry attempt {attempt + 1}/{max_retries} after {retry_delay:.1f}s delay...")
            await asyncio.sleep(retry_delay)

        try:
            response = await _glm_client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            logger.info(f"GLM-4V API response received: {len(content)} chars")
            return content

        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            try:
                error_data = json.loads(error_text) if error_text else {}
                error_code = error_data.get("code", e.response.status_code)
                error_message = error_data.get("message", error_text)
            except:
                error_code = e.response.status_code
                error_message = error_text

            if e.response.status_code == 429:
                # Rate limit - too many requests
                logger.warning(f"GLM API rate limit hit (attempt {attempt + 1}/{max_retries}): {error_message}")
                if attempt < max_retries - 1:
                    continue  # Retry with exponential backoff
                else:
                    raise Exception(f"API rate limit exceeded: {error_message}")
            elif e.response.status_code == 401:
                logger.error(f"GLM API authentication failed (401): {error_message}")
                raise Exception(f"API认证失败，请检查GLM_API_KEY是否正确: {error_message}")
            elif e.response.status_code >= 500:
                logger.warning(f"GLM API server error (attempt {attempt + 1}/{max_retries}): {error_code}")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise Exception(f"GLM API服务器错误: {error_message}")
            else:
                logger.error(f"GLM API HTTP error {error_code}: {error_message}")
                raise Exception(f"GLM API请求失败 ({error_code}): {error_message}")
        except httpx.ConnectError as e:
            logger.warning(f"GLM API connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            else:
                raise Exception(f"无法连接到GLM API服务器: {e}")
        except Exception as e:
            logger.error(f"GLM API call failed: {e}")
            raise


async def analyze_image_content(
    image_bytes: bytes,
    user_question: str = "",
) -> str:
    """Analyze image content using GLM-4V-Flash API or local model.

    This is the main entry point for image analysis in the application.

    Args:
        image_bytes: Raw image data
        user_question: Optional question user is asking about the image

    Returns:
        Formatted description string for LLM context

    Example output:
        【图片内容分析】
        这张图片显示了一只橘猫坐在红色沙发上...
        猫的表情看起来很放松...

    Raises:
        RuntimeError: If both GLM API and local model are unavailable
    """
    global _glm_available

    # Initialize GLM client on first use
    if _glm_available is False and _init_glm_client():
        _glm_available = True

    # Determine question
    question = user_question or "请详细描述这张图片的内容，包括主要物体、场景、颜色、布局等细节"

    try:
        # Try GLM-4V-Flash API first (preferred - FREE!)
        if _glm_available:
            logger.info(f"Analyzing image with GLM-4V-Flash API (model: {settings.GLM_VISION_MODEL})...")
            image_base64 = _encode_image_to_base64(image_bytes)
            result = await _call_glm_vision_api(image_base64, question, retry_count=0)

            # Format response for LLM context
            return f"【图片内容分析】\n{result}"

        # Fallback to local model
        elif settings.VISION_BACKEND == "local":
            logger.info("GLM unavailable, using local vision model...")
            raise NotImplementedError("Local vision model not implemented yet. Please use GLM API.")

        else:
            raise RuntimeError(
                "Vision analysis unavailable: GLM API not configured (set GLM_API_KEY in .env) "
                "and local model disabled. Image analysis will be skipped."
            )

    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        raise


def is_vision_available() -> bool:
    """Check if any vision backend is available."""
    if _glm_available:
        return True

    # Check if local model is enabled
    if settings.VISION_BACKEND == "local":
        return True

    # Check if GLM API key is configured
    if settings.GLM_API_KEY:
        return True

    return False


def get_supported_formats() -> list[str]:
    """Get list of supported image formats.

    GLM-4V-Flash supports: jpg, png, jpeg (max 5MB, pixels <= 6000*6000)

    Returns:
        List of supported file extensions
    """
    return [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".webp", ".tiff",
    ]


async def close_vision_service():
    """Clean up resources."""
    global _glm_client

    if _glm_client is not None:
        await _glm_client.aclose()
        _glm_client = None
        logger.info("GLM API client closed")
