"""LLM Service using Llama.cpp for Mac M3 Metal acceleration.

This service wraps llama-cpp-python for optimized inference on Apple Silicon.
Supports multiple model types (Qwen, Mistral, Llama, etc.).
"""
import asyncio
import ast
import base64
import html
import json
import logging
import math
import operator
import re
import random
import secrets
import string
import time
import uuid
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from pathlib import Path
from typing import Optional, Generator, AsyncGenerator, Any

from app.core.config import settings, MODELS_DIR

logger = logging.getLogger(__name__)

# Global LLM instance
_llm_instance: Optional["Llama"] = None
_openai_client = None
_vllm_probe_cache: tuple[float, bool, str | None] | None = None

# Chat templates for different model types
CHAT_TEMPLATES = {
    "qwen": (
        "<|im_start|>system\n{system_prompt}<|im_end|>\n"
        "<|im_start|>user\n{context}{question}<|im_end|>\n"
        "<|im_start|>assistant\n"
    ),
    "mistral": (
        "[INST] <<SYS>>\n"
        "{system_prompt}\n"
        "<</SYS>>\n\n"
        "{context}{question} [/INST]"
    ),
    "llama": (
        "[INST] <<SYS>>\n"
        "{system_prompt}\n"
        "<</SYS>>\n\n"
        "{context}{question} [/INST]"
    ),
}

BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get current time in a specified timezone (default UTC).",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "IANA timezone, e.g. Asia/Shanghai"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_beijing_time",
            "description": "Get current Beijing time (Asia/Shanghai).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location (city name).",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name, e.g. Tokyo"},
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_wind_chill",
            "description": "Calculate wind chill from temperature and wind speed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "temperature": {"type": "number", "description": "Air temperature"},
                    "wind_speed_kmh": {"type": "number", "description": "Wind speed in km/h"},
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["temperature", "wind_speed_kmh"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "math_calculator",
            "description": "Evaluate a basic math expression safely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search latest web news by keyword (real-time oriented).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "limit": {"type": "integer", "description": "Max results (1-10), default 5"},
                    "freshness": {
                        "type": "string",
                        "enum": ["hour", "day", "week", "month", "any"],
                        "description": "Time window filter, default day",
                    },
                    "market": {"type": "string", "description": "Market/region code, e.g. en-US, zh-CN"},
                    "language": {"type": "string", "description": "Language hint, e.g. en-US, zh-CN"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web_realtime",
            "description": "Search real-time web news and latest headlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "limit": {"type": "integer", "description": "Max results (1-10), default 5"},
                    "freshness": {
                        "type": "string",
                        "enum": ["hour", "day", "week", "month", "any"],
                        "description": "Time window filter, default day",
                    },
                    "market": {"type": "string", "description": "Market/region code, e.g. en-US, zh-CN"},
                    "language": {"type": "string", "description": "Language hint, e.g. en-US, zh-CN"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Get FX exchange rate and optional amount conversion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_currency": {"type": "string", "description": "Base currency code, e.g. USD"},
                    "target_currency": {"type": "string", "description": "Target currency code, e.g. CNY"},
                    "amount": {"type": "number", "description": "Optional amount to convert"},
                },
                "required": ["base_currency", "target_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stock_quote",
            "description": "Get real-time market quote for a stock/ETF ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. AAPL, TSLA, 0700.HK"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_unit",
            "description": "Convert between common units (temperature, length, weight).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "Input numeric value"},
                    "from_unit": {"type": "string", "description": "Source unit, e.g. km, celsius, kg"},
                    "to_unit": {"type": "string", "description": "Target unit, e.g. mile, fahrenheit, lb"},
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_info",
            "description": "Get weekday/calendar info for a date in specified timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Optional date: YYYY-MM-DD, default today"},
                    "timezone": {"type": "string", "description": "IANA timezone, default Asia/Shanghai"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "text_stats",
            "description": "Count characters/words/lines and basic text statistics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to analyze"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_uuid",
            "description": "Generate a UUID string for identifiers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "version": {"type": "integer", "description": "UUID version, currently supports 4"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "random_number",
            "description": "Generate random integer in [min, max].",
            "parameters": {
                "type": "object",
                "properties": {
                    "min": {"type": "integer", "description": "Lower bound (inclusive), default 1"},
                    "max": {"type": "integer", "description": "Upper bound (inclusive), default 100"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "coin_flip",
            "description": "Flip a coin multiple times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of flips, default 1"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": "Roll dice with configurable sides and count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sides": {"type": "integer", "description": "Dice sides, default 6"},
                    "count": {"type": "integer", "description": "How many dice to roll, default 1"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_password",
            "description": "Generate a random password without external API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "length": {"type": "integer", "description": "Password length, default 16"},
                    "include_symbols": {"type": "boolean", "description": "Include symbols, default true"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hash_text",
            "description": "Hash text using md5/sha1/sha256/sha512.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Input text"},
                    "algorithm": {"type": "string", "description": "md5 | sha1 | sha256 | sha512 (default sha256)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "base64_codec",
            "description": "Encode/decode base64 text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "description": "encode | decode"},
                    "text": {"type": "string", "description": "Input text"},
                },
                "required": ["mode", "text"],
            },
        },
    },
]


SAFE_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

SAFE_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


# Common Chinese city aliases for weather tool geocoding fallback.
# Open-Meteo geocoding is more stable with English city names.
CN_CITY_ALIAS_TO_EN = {
    "北京": "Beijing",
    "北京市": "Beijing",
    "上海": "Shanghai",
    "上海市": "Shanghai",
    "广州": "Guangzhou",
    "广州市": "Guangzhou",
    "深圳": "Shenzhen",
    "深圳市": "Shenzhen",
    "杭州": "Hangzhou",
    "杭州市": "Hangzhou",
    "南京": "Nanjing",
    "南京市": "Nanjing",
    "苏州": "Suzhou",
    "苏州市": "Suzhou",
    "成都": "Chengdu",
    "成都市": "Chengdu",
    "重庆": "Chongqing",
    "重庆市": "Chongqing",
    "武汉": "Wuhan",
    "武汉市": "Wuhan",
    "西安": "Xi'an",
    "西安市": "Xi'an",
    "天津": "Tianjin",
    "天津市": "Tianjin",
    "青岛": "Qingdao",
    "青岛市": "Qingdao",
    "大连": "Dalian",
    "大连市": "Dalian",
    "沈阳": "Shenyang",
    "沈阳市": "Shenyang",
    "哈尔滨": "Harbin",
    "哈尔滨市": "Harbin",
    "长春": "Changchun",
    "长春市": "Changchun",
    "郑州": "Zhengzhou",
    "郑州市": "Zhengzhou",
    "济南": "Jinan",
    "济南市": "Jinan",
    "福州": "Fuzhou",
    "福州市": "Fuzhou",
    "厦门": "Xiamen",
    "厦门市": "Xiamen",
    "合肥": "Hefei",
    "合肥市": "Hefei",
    "昆明": "Kunming",
    "昆明市": "Kunming",
    "南昌": "Nanchang",
    "南昌市": "Nanchang",
    "南宁": "Nanning",
    "南宁市": "Nanning",
    "贵阳": "Guiyang",
    "贵阳市": "Guiyang",
    "石家庄": "Shijiazhuang",
    "石家庄市": "Shijiazhuang",
    "太原": "Taiyuan",
    "太原市": "Taiyuan",
    "呼和浩特": "Hohhot",
    "呼和浩特市": "Hohhot",
    "乌鲁木齐": "Urumqi",
    "乌鲁木齐市": "Urumqi",
    "拉萨": "Lhasa",
    "拉萨市": "Lhasa",
    "银川": "Yinchuan",
    "银川市": "Yinchuan",
    "西宁": "Xining",
    "西宁市": "Xining",
    "海口": "Haikou",
    "海口市": "Haikou",
    "三亚": "Sanya",
    "三亚市": "Sanya",
}

UNIT_ALIASES = {
    "c": "celsius",
    "centigrade": "celsius",
    "celsius": "celsius",
    "f": "fahrenheit",
    "fahrenheit": "fahrenheit",
    "k": "kelvin",
    "kelvin": "kelvin",
    "m": "meter",
    "meter": "meter",
    "meters": "meter",
    "metre": "meter",
    "metres": "meter",
    "km": "kilometer",
    "kilometer": "kilometer",
    "kilometers": "kilometer",
    "kilometre": "kilometer",
    "kilometres": "kilometer",
    "cm": "centimeter",
    "centimeter": "centimeter",
    "centimeters": "centimeter",
    "mm": "millimeter",
    "millimeter": "millimeter",
    "millimeters": "millimeter",
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "ft": "foot",
    "foot": "foot",
    "feet": "foot",
    "yd": "yard",
    "yard": "yard",
    "yards": "yard",
    "mi": "mile",
    "mile": "mile",
    "miles": "mile",
    "g": "gram",
    "gram": "gram",
    "grams": "gram",
    "kg": "kilogram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "lb": "pound",
    "lbs": "pound",
    "pound": "pound",
    "pounds": "pound",
    "oz": "ounce",
    "ounce": "ounce",
    "ounces": "ounce",
}

LENGTH_TO_METER = {
    "millimeter": 0.001,
    "centimeter": 0.01,
    "meter": 1.0,
    "kilometer": 1000.0,
    "inch": 0.0254,
    "foot": 0.3048,
    "yard": 0.9144,
    "mile": 1609.344,
}

WEIGHT_TO_GRAM = {
    "gram": 1.0,
    "kilogram": 1000.0,
    "pound": 453.59237,
    "ounce": 28.349523125,
}


def get_llm() -> "Llama":
    """Get or initialize the LLM instance (singleton pattern)."""
    global _llm_instance
    if _llm_instance is None:
        from llama_cpp import Llama

        model_path = MODELS_DIR / Path(settings.MODEL_PATH).name

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found at {model_path}. "
                f"Please download the model file and place it in {MODELS_DIR}"
            )

        _llm_instance = Llama(
            model_path=str(model_path),
            n_gpu_layers=settings.N_GPU_LAYERS,  # -1 = offload all to Metal GPU
            n_ctx=settings.N_CTX,
            f16_kv=settings.F16_KV,
            verbose=False,
        )

    return _llm_instance


def get_openai_client():
    """Get or initialize OpenAI-compatible client for vLLM."""
    global _openai_client
    if _openai_client is None:
        import httpx
        from openai import OpenAI

        # Force direct connection to vLLM endpoint; avoid inheriting proxy vars
        # from user shell (common cause of localhost tunnel failures).
        http_client = httpx.Client(
            timeout=settings.VLLM_TIMEOUT_SECONDS,
            trust_env=False,
        )

        _openai_client = OpenAI(
            base_url=settings.VLLM_BASE_URL,
            api_key=settings.VLLM_API_KEY,
            http_client=http_client,
        )
    return _openai_client


def get_active_model_name() -> str:
    """Get the effective model name currently used by the backend."""
    if settings.LLM_PROVIDER == "vllm":
        return settings.VLLM_MODEL
    return Path(settings.MODEL_PATH).name


def probe_vllm_connection() -> tuple[bool, str | None]:
    """Check remote vLLM availability and model visibility."""
    global _vllm_probe_cache

    if settings.LLM_PROVIDER != "vllm":
        return True, None

    now = time.monotonic()
    if _vllm_probe_cache is not None:
        cache_ts, cache_ok, cache_reason = _vllm_probe_cache
        if now - cache_ts <= settings.VLLM_HEALTH_CACHE_SECONDS:
            return cache_ok, cache_reason

    try:
        import httpx

        models_url = f"{settings.VLLM_BASE_URL.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {settings.VLLM_API_KEY}"}
        with httpx.Client(
            timeout=settings.VLLM_PROBE_TIMEOUT_SECONDS,
            trust_env=False,
        ) as client:
            response = client.get(models_url, headers=headers)
            response.raise_for_status()
            payload = response.json()
            available_models = {
                item.get("id")
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
    except Exception as exc:
        reason = f"vLLM endpoint unreachable: {exc}"
        _vllm_probe_cache = (now, False, reason)
        return False, reason

    if settings.VLLM_MODEL not in available_models:
        reason_text = f"Configured VLLM_MODEL='{settings.VLLM_MODEL}' not found in /v1/models"
        _vllm_probe_cache = (now, False, reason_text)
        return False, reason_text

    _vllm_probe_cache = (now, True, None)
    return True, None


def get_stop_tokens() -> list[str]:
    """Get appropriate stop tokens based on model type."""
    template_type = settings.CHAT_TEMPLATE_TYPE
    if template_type == "qwen":
        # Qwen2.5 uses <|im_end|> as stop token
        return ["<|im_end|>"]
    else:  # mistral, llama
        return ["[/INST]"]


def _format_user_text(question: str, context: str = "") -> str:
    """Build unified user text for both text-only and multimodal requests."""
    if context:
        return f"【参考文档】\n{context}\n\n【用户问题】\n{question}"
    return question


def _build_data_url_image(image_data: str, image_format: str | None = None) -> str:
    """Convert raw base64 image to data URL format expected by OpenAI-compatible APIs."""
    if image_data.startswith("data:image/"):
        return image_data

    fmt = (image_format or "png").lower()
    return f"data:image/{fmt};base64,{image_data}"


def _collect_multimodal_images(
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
) -> list[tuple[str, str | None]]:
    """Collect single/multi image inputs into one normalized list."""
    images: list[tuple[str, str | None]] = []
    if image_data:
        images.append((image_data, image_format))

    formats = image_format_list or []
    for idx, payload in enumerate(image_data_list or []):
        if not payload:
            continue
        fmt = formats[idx] if idx < len(formats) else None
        images.append((payload, fmt))
    return images


def _collect_multimodal_audio(
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
) -> list[str]:
    """Collect single/multi audio URLs into one normalized list."""
    audios: list[str] = []
    if audio_url:
        audios.append(audio_url)

    for payload in audio_url_list or []:
        if not payload:
            continue
        audios.append(payload)
    return audios


def _collect_multimodal_videos(
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
) -> list[str]:
    """Collect single/multi video URLs into one normalized list."""
    videos: list[str] = []
    if video_url:
        videos.append(video_url)

    for payload in video_url_list or []:
        if not payload:
            continue
        videos.append(payload)
    return videos


def _build_vllm_user_content(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
):
    """Build user content payload for vLLM chat completion request."""
    user_text = _format_user_text(question, context)
    images = _collect_multimodal_images(
        image_data=image_data,
        image_format=image_format,
        image_data_list=image_data_list,
        image_format_list=image_format_list,
    )
    audios = _collect_multimodal_audio(
        audio_url=audio_url,
        audio_url_list=audio_url_list,
    )
    videos = _collect_multimodal_videos(
        video_url=video_url,
        video_url_list=video_url_list,
    )
    if not images and not audios and not videos:
        return user_text

    # Keep official Gemma4 multimodal ordering: mm blocks first, text block last.
    blocks: list[dict[str, object]] = []
    for payload, fmt in images:
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": _build_data_url_image(payload, fmt)},
            }
        )
    for video in videos:
        blocks.append(
            {
                "type": "video_url",
                "video_url": {"url": video},
            }
        )
    for audio in audios:
        blocks.append(
            {
                "type": "audio_url",
                "audio_url": {"url": audio},
            }
        )
    blocks.append({"type": "text", "text": user_text})
    return blocks


def _build_extra_body(enable_thinking: bool) -> dict | None:
    """Build extra body fields for Gemma4 optional modes."""
    if not enable_thinking:
        return None
    return {
        "chat_template_kwargs": {
            "enable_thinking": True,
        }
    }


def _get_value(obj: Any, key: str) -> Any:
    """Read a field from dict/object safely."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_text_field(value: Any) -> str:
    """Extract text from OpenAI-compatible content field."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
                continue

            item_text = _get_value(item, "text") or _get_value(item, "content")
            if isinstance(item_text, str):
                parts.append(item_text)
        return "".join(parts)
    return ""


def _extract_reasoning_and_answer(message: Any) -> tuple[str, str]:
    """Extract reasoning and final answer from non-stream message payload."""
    answer = _extract_text_field(_get_value(message, "content")).strip()

    reasoning = ""
    for key in ("reasoning_content", "reasoning", "reasoning_text"):
        candidate = _extract_text_field(_get_value(message, key)).strip()
        if candidate:
            reasoning = candidate
            break

    if not reasoning:
        model_extra = _get_value(message, "model_extra")
        if isinstance(model_extra, dict):
            for key in ("reasoning_content", "reasoning", "reasoning_text"):
                candidate = _extract_text_field(model_extra.get(key)).strip()
                if candidate:
                    reasoning = candidate
                    break

    return reasoning, answer


def _format_thinking_output(reasoning: str, answer: str) -> str:
    """Merge reasoning + answer into one text stream for downstream parser/UI."""
    if reasoning and answer:
        return f"thought {reasoning}\n\nFinal answer:\n{answer}"
    if reasoning:
        return f"thought {reasoning}"
    return answer


def _extract_delta_reasoning(delta: Any) -> str:
    """Extract reasoning token chunk from streaming delta payload."""
    for key in ("reasoning_content", "reasoning", "reasoning_text"):
        token = _extract_text_field(_get_value(delta, key))
        if token:
            return token

    model_extra = _get_value(delta, "model_extra")
    if isinstance(model_extra, dict):
        for key in ("reasoning_content", "reasoning", "reasoning_text"):
            token = _extract_text_field(model_extra.get(key))
            if token:
                return token

    return ""


def _extract_delta_answer(delta: Any) -> str:
    """Extract final answer token chunk from streaming delta payload."""
    return _extract_text_field(_get_value(delta, "content"))


def _resolve_generation_params(
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
) -> tuple[int, float, float]:
    """Resolve request-level generation params with backend safety bounds."""
    resolved_max_tokens = settings.MAX_TOKENS if max_tokens is None else int(max_tokens)
    if resolved_max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")
    resolved_max_tokens = min(resolved_max_tokens, settings.MAX_TOKENS_HARD_LIMIT)

    resolved_temperature = settings.TEMPERATURE if temperature is None else float(temperature)
    resolved_top_p = settings.TOP_P if top_p is None else float(top_p)
    return resolved_max_tokens, resolved_temperature, resolved_top_p


def _safe_eval_math(expression: str) -> float:
    """Safely evaluate basic arithmetic expression."""
    node = ast.parse(expression, mode="eval")

    def _eval(current: ast.AST) -> float:
        if isinstance(current, ast.Expression):
            return _eval(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, (int, float)):
            return float(current.value)
        if isinstance(current, ast.BinOp) and type(current.op) in SAFE_BINARY_OPS:
            left = _eval(current.left)
            right = _eval(current.right)
            return float(SAFE_BINARY_OPS[type(current.op)](left, right))
        if isinstance(current, ast.UnaryOp) and type(current.op) in SAFE_UNARY_OPS:
            value = _eval(current.operand)
            return float(SAFE_UNARY_OPS[type(current.op)](value))
        raise ValueError("Unsupported expression")

    return _eval(node)


def _is_chinese_text(text: str) -> bool:
    """Return True when text contains CJK characters."""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _strip_china_city_suffix(text: str) -> str:
    """Strip common Chinese administrative suffixes for better alias matching."""
    cleaned = re.sub(
        r"(特别行政区|维吾尔自治区|回族自治区|壮族自治区|自治区|自治州|地区|盟|省|市)$",
        "",
        text,
    )
    return cleaned.strip()


def _build_weather_location_candidates(raw_location: str) -> list[str]:
    """Build stable geocoding candidates; prioritize English alias for Chinese city names."""
    base = (raw_location or "").strip()
    if not base:
        return []

    candidates: list[str] = []

    def _push(value: str | None) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    normalized_no_space = re.sub(r"\s+", "", base)
    stripped = _strip_china_city_suffix(normalized_no_space)

    _push(CN_CITY_ALIAS_TO_EN.get(base))
    _push(CN_CITY_ALIAS_TO_EN.get(normalized_no_space))
    _push(CN_CITY_ALIAS_TO_EN.get(stripped))

    # Keep original Chinese query as fallback when alias is not covered.
    _push(base)
    _push(normalized_no_space)
    _push(stripped)
    if stripped:
        _push(f"{stripped}市")

    return candidates[:6]


def _build_time_payload_for_timezone(timezone_name: str) -> dict[str, Any]:
    """Build stable time payload for a target timezone."""
    now_utc = datetime.now(timezone.utc)
    target_tz = ZoneInfo(timezone_name)
    local_time = now_utc.astimezone(target_tz)
    return {
        "timezone": timezone_name,
        "current_time_local": local_time.isoformat(),
        "current_time_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "utc_offset": local_time.strftime("%z"),
        "unix_timestamp": int(now_utc.timestamp()),
    }


def _normalize_unit_name(unit: str) -> str:
    """Normalize unit token to canonical form."""
    return UNIT_ALIASES.get(unit.strip().lower(), unit.strip().lower())


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert temperature units via Celsius base."""
    if from_unit == to_unit:
        return value

    if from_unit == "celsius":
        celsius = value
    elif from_unit == "fahrenheit":
        celsius = (value - 32.0) * 5.0 / 9.0
    elif from_unit == "kelvin":
        celsius = value - 273.15
    else:
        raise ValueError(f"unsupported temperature unit: {from_unit}")

    if to_unit == "celsius":
        return celsius
    if to_unit == "fahrenheit":
        return celsius * 9.0 / 5.0 + 32.0
    if to_unit == "kelvin":
        return celsius + 273.15
    raise ValueError(f"unsupported temperature unit: {to_unit}")


def _parse_limited_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    """Parse integer with bounded range and safe fallback."""
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalize_news_freshness(raw_freshness: Any) -> tuple[str, int | None]:
    """Normalize freshness token for realtime news search."""
    token = str(raw_freshness or "").strip().lower()
    mapping: dict[str, tuple[str, int | None]] = {
        "hour": ("hour", 3600),
        "1h": ("hour", 3600),
        "past_hour": ("hour", 3600),
        "过去1小时": ("hour", 3600),
        "最近1小时": ("hour", 3600),
        "小时": ("hour", 3600),
        "day": ("day", 86400),
        "1d": ("day", 86400),
        "24h": ("day", 86400),
        "today": ("day", 86400),
        "past_day": ("day", 86400),
        "过去24小时": ("day", 86400),
        "最近1天": ("day", 86400),
        "今天": ("day", 86400),
        "week": ("week", 604800),
        "7d": ("week", 604800),
        "past_week": ("week", 604800),
        "最近一周": ("week", 604800),
        "过去7天": ("week", 604800),
        "month": ("month", 2592000),
        "30d": ("month", 2592000),
        "past_month": ("month", 2592000),
        "最近一月": ("month", 2592000),
        "过去30天": ("month", 2592000),
        "any": ("any", None),
        "all": ("any", None),
        "latest": ("day", 86400),
        "实时": ("day", 86400),
        "不限": ("any", None),
        "全部": ("any", None),
    }
    return mapping.get(token, ("day", 86400))


def _derive_market_from_language(raw_language: Any) -> str:
    """Derive default market from language token."""
    language = str(raw_language or "").strip().replace("_", "-").lower()
    if not language:
        return "en-US"

    aliases = {
        "en": "en-US",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hant": "zh-TW",
        "ja": "ja-JP",
        "ko": "ko-KR",
    }
    if language in aliases:
        return aliases[language]

    match = re.match(r"^([a-z]{2})-([a-z]{2})$", language)
    if match:
        return f"{match.group(1)}-{match.group(2).upper()}"

    return "en-US"


def _resolve_news_locale(market_value: Any, language_value: Any) -> tuple[str, str]:
    """Resolve market/language pair with sane defaults."""
    market = str(market_value or "").strip().replace("_", "-")
    language = str(language_value or "").strip().replace("_", "-")

    if not language:
        language = market or "en-US"
    if not market:
        market = _derive_market_from_language(language)

    return market, language


def _clean_html_text(raw_text: Any) -> str:
    """Decode html entities and strip simple tags."""
    text = html.unescape(str(raw_text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _decode_bing_news_redirect(raw_url: Any) -> str:
    """Decode Bing news redirect URL to original article URL when possible."""
    candidate = str(raw_url or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if "bing.com" in (parsed.netloc or "").lower() and parsed.path.endswith("/news/apiclick.aspx"):
        params = parse_qs(parsed.query)
        original = (params.get("url") or [""])[0]
        if original:
            return unquote(original)
    return candidate


def _parse_news_datetime_utc(raw_value: Any) -> datetime | None:
    """Parse RFC822-like date string into UTC datetime."""
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_rss_items(rss_text: str, *, decode_bing_redirect: bool) -> list[dict[str, Any]]:
    """Parse RSS XML text into normalized item objects."""
    body = str(rss_text or "").strip()
    if not body:
        raise ValueError("empty rss body")

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        preview = body[:120].replace("\n", " ")
        raise ValueError(f"rss parse error: {exc}; prefix={preview!r}") from exc

    items: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        if not isinstance(item.tag, str):
            continue
        title = _clean_html_text(item.findtext("title"))
        if not title:
            continue

        raw_link = _clean_html_text(item.findtext("link"))
        if decode_bing_redirect:
            article_url = _decode_bing_news_redirect(raw_link)
        else:
            article_url = raw_link

        raw_pub_date = _clean_html_text(item.findtext("pubDate"))
        published_dt = _parse_news_datetime_utc(raw_pub_date)
        published_iso = (
            published_dt.isoformat().replace("+00:00", "Z")
            if published_dt is not None
            else None
        )

        source_name = ""
        for child in list(item):
            if not isinstance(child.tag, str):
                continue
            if child.tag.lower().endswith("source"):
                source_name = _clean_html_text(child.text)
                if source_name:
                    break
        if not source_name:
            source_name = "Unknown"

        snippet = _clean_html_text(item.findtext("description"))
        if len(snippet) > 280:
            snippet = snippet[:277] + "..."

        items.append(
            {
                "title": title,
                "url": article_url or raw_link,
                "source": source_name,
                "published_at_utc": published_iso,
                "snippet": snippet or None,
                "_published_dt": published_dt,
            }
        )
    return items


def _filter_news_items(
    *,
    all_items: list[dict[str, Any]],
    now_utc: datetime,
    normalized_freshness: str,
    max_age_seconds: int | None,
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Apply freshness filter and limit, with graceful fallback note."""
    if max_age_seconds is None:
        filtered_items = all_items
    else:
        filtered_items = []
        for item in all_items:
            published_dt = item.get("_published_dt")
            if isinstance(published_dt, datetime):
                age_seconds = (now_utc - published_dt).total_seconds()
                if age_seconds <= max_age_seconds:
                    filtered_items.append(item)

    fallback_note: str | None = None
    if not filtered_items and all_items and max_age_seconds is not None:
        fallback_note = (
            f"No results matched freshness={normalized_freshness}; returned latest available headlines."
        )
        filtered_items = all_items

    results: list[dict[str, Any]] = []
    for item in filtered_items[:limit]:
        clean_item = dict(item)
        clean_item.pop("_published_dt", None)
        results.append(clean_item)

    return results, fallback_note


def _parse_baidu_time_to_utc(raw_text: str, now_utc: datetime) -> datetime | None:
    """Best-effort parse for common Baidu news time strings."""
    text = str(raw_text or "").strip()
    if not text:
        return None

    now_cn = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))

    minute_match = re.search(r"(\d+)\s*分钟前", text)
    if minute_match:
        return (now_cn - timedelta(minutes=int(minute_match.group(1)))).astimezone(timezone.utc)

    hour_match = re.search(r"(\d+)\s*小时前", text)
    if hour_match:
        return (now_cn - timedelta(hours=int(hour_match.group(1)))).astimezone(timezone.utc)

    day_match = re.search(r"(\d+)\s*天前", text)
    if day_match:
        return (now_cn - timedelta(days=int(day_match.group(1)))).astimezone(timezone.utc)

    full_date_match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?", text)
    if full_date_match:
        year = int(full_date_match.group(1))
        month = int(full_date_match.group(2))
        day = int(full_date_match.group(3))
        try:
            dt_cn = datetime(year, month, day, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            return dt_cn.astimezone(timezone.utc)
        except Exception:
            return None

    short_date_match = re.search(r"(\d{1,2})[月/-](\d{1,2})日?", text)
    if short_date_match:
        month = int(short_date_match.group(1))
        day = int(short_date_match.group(2))
        try:
            dt_cn = datetime(now_cn.year, month, day, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            return dt_cn.astimezone(timezone.utc)
        except Exception:
            return None

    return None


def _extract_baidu_news_items(html_text: str, *, now_utc: datetime) -> list[dict[str, Any]]:
    """Parse Baidu news search HTML into normalized item objects."""
    body = str(html_text or "").strip()
    if not body:
        raise ValueError("empty html body")
    if (
        "百度安全验证" in body
        or "wappass.baidu.com/static/captcha" in body
        or "mkdjump_v2" in body
    ):
        raise ValueError("baidu blocked by security verification")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    candidate_blocks = soup.select("div.result, div.c-container, div[class*='result']")
    for block in candidate_blocks:
        anchor = block.select_one("h3 a[href], a[href]")
        if anchor is None:
            continue
        url = str(anchor.get("href") or "").strip()
        title = _clean_html_text(anchor.get_text(" ", strip=True))
        if not url.startswith("http") or not title:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        meta_text = _clean_html_text(block.get_text(" ", strip=True))
        published_dt = _parse_baidu_time_to_utc(meta_text, now_utc=now_utc)
        published_iso = (
            published_dt.isoformat().replace("+00:00", "Z")
            if published_dt is not None
            else None
        )

        source_name = "baidu.com"
        source_match = re.search(r"([^\s]{1,24})\s+\d{1,4}[年/-]\d{1,2}", meta_text)
        if source_match:
            source_name = source_match.group(1)

        snippet = _clean_html_text(meta_text)
        if len(snippet) > 280:
            snippet = snippet[:277] + "..."

        items.append(
            {
                "title": title,
                "url": url,
                "source": source_name,
                "published_at_utc": published_iso,
                "snippet": snippet or None,
                "_published_dt": published_dt,
            }
        )

    if not items:
        raise ValueError("baidu returned no parsable results")
    return items


def _search_bing_news_realtime(
    *,
    query: str,
    limit: int,
    freshness: Any,
    market: str,
    language: str,
) -> dict[str, Any]:
    """Search latest headlines from realtime providers with freshness filtering."""
    import httpx

    normalized_freshness, max_age_seconds = _normalize_news_freshness(freshness)
    now_utc = datetime.now(timezone.utc)
    timeout = httpx.Timeout(
        timeout=settings.WEATHER_TOOL_TIMEOUT_SECONDS,
        connect=min(8.0, settings.WEATHER_TOOL_TIMEOUT_SECONDS),
    )
    headers = {"User-Agent": "AssistantBot/0.1 (+https://www.bing.com/news)"}
    market, language = _resolve_news_locale(market, language)
    market_country = "US"
    market_parts = market.split("-")
    if len(market_parts) >= 2 and market_parts[1]:
        market_country = market_parts[1].upper()

    google_ceid_lang = language
    language_lower = language.lower()
    if language_lower in {"zh", "zh-cn", "zh-hans"}:
        google_ceid_lang = "zh-Hans"
    elif language_lower in {"zh-tw", "zh-hk", "zh-hant"}:
        google_ceid_lang = "zh-Hant"

    provider_attempts = [
        {
            "provider": "bing_news_rss",
            "source": "bing.com/news (RSS)",
            "url": "https://www.bing.com/news/search",
            "params": {
                "q": query,
                "format": "rss",
                "mkt": market,
                "setlang": language,
                "qft": 'sortbydate="1"',
            },
            "decode_bing_redirect": True,
            "parser": "rss",
        },
        {
            "provider": "google_news_rss",
            "source": "news.google.com (RSS)",
            "url": "https://news.google.com/rss/search",
            "params": {
                "q": query,
                "hl": language,
                "gl": market_country,
                "ceid": f"{market_country}:{google_ceid_lang}",
            },
            "decode_bing_redirect": False,
            "parser": "rss",
        },
        {
            "provider": "baidu_news_search",
            "source": "news.baidu.com (search)",
            "url": "https://news.baidu.com/ns",
            "params": {
                "word": query,
                "tn": "news",
                "from": "news",
                "cl": "2",
                "rn": str(max(10, limit * 3)),
                "ct": "1",
            },
            "parser": "baidu_html",
        },
    ]

    provider_errors: dict[str, str] = {}
    with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False, headers=headers) as client:
        for attempt in provider_attempts:
            provider = str(attempt["provider"])
            try:
                response = client.get(str(attempt["url"]), params=attempt["params"])
                response.raise_for_status()
                parser_name = str(attempt.get("parser") or "rss")
                if parser_name == "baidu_html":
                    all_items = _extract_baidu_news_items(response.text, now_utc=now_utc)
                else:
                    all_items = _extract_rss_items(
                        response.text,
                        decode_bing_redirect=bool(attempt.get("decode_bing_redirect", False)),
                    )
                if not all_items:
                    raise ValueError("provider returned 0 items")

                results, fallback_note = _filter_news_items(
                    all_items=all_items,
                    now_utc=now_utc,
                    normalized_freshness=normalized_freshness,
                    max_age_seconds=max_age_seconds,
                    limit=limit,
                )

                payload: dict[str, Any] = {
                    "query": query,
                    "freshness": normalized_freshness,
                    "market": market,
                    "language": language,
                    "count": len(results),
                    "source": attempt["source"],
                    "provider": provider,
                    "searched_at_utc": now_utc.isoformat().replace("+00:00", "Z"),
                    "results": results,
                }
                if fallback_note:
                    payload["note"] = fallback_note
                if provider_errors:
                    payload["provider_warnings"] = provider_errors
                return payload
            except Exception as exc:
                provider_errors[provider] = str(exc)

    raise RuntimeError(f"all realtime providers failed: {provider_errors}")


def _search_hn_news_fallback(query: str, limit: int) -> dict[str, Any]:
    """Fallback news search through HN Algolia."""
    import httpx

    timeout = httpx.Timeout(
        timeout=settings.WEATHER_TOOL_TIMEOUT_SECONDS,
        connect=min(8.0, settings.WEATHER_TOOL_TIMEOUT_SECONDS),
    )
    params = {"query": query, "tags": "story", "hitsPerPage": limit}
    url = f"https://hn.algolia.com/api/v1/search?{urlencode(params)}"
    with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()

    hits = payload.get("hits") or []
    items = []
    for item in hits:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "author": item.get("author"),
                "points": item.get("points"),
                "published_at_utc": item.get("created_at"),
            }
        )
        if len(items) >= limit:
            break

    return {
        "query": query,
        "count": len(items),
        "source": "hn.algolia.com (fallback)",
        "results": items,
    }


def _execute_builtin_tool(tool_name: str, arguments_json: str) -> str:
    """Execute built-in tools and return tool output text."""
    try:
        arguments = json.loads(arguments_json) if arguments_json else {}
        if not isinstance(arguments, dict):
            arguments = {}
    except Exception:
        arguments = {}

    if tool_name == "get_current_time":
        tz = str(arguments.get("timezone") or "").strip()
        if not tz:
            tz = "UTC"
        try:
            return json.dumps(_build_time_payload_for_timezone(tz), ensure_ascii=False)
        except Exception:
            # Keep backward compatibility for invalid timezone values.
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return json.dumps(
                {
                    "error": f"invalid timezone: {tz}",
                    "current_time_utc": now_iso,
                    "timezone_hint": tz,
                },
                ensure_ascii=False,
            )

    if tool_name == "get_beijing_time":
        return json.dumps(_build_time_payload_for_timezone("Asia/Shanghai"), ensure_ascii=False)

    if tool_name == "convert_unit":
        try:
            value = float(arguments.get("value"))
        except Exception:
            return json.dumps({"error": "value must be a number"}, ensure_ascii=False)

        from_unit = _normalize_unit_name(str(arguments.get("from_unit") or ""))
        to_unit = _normalize_unit_name(str(arguments.get("to_unit") or ""))
        if not from_unit or not to_unit:
            return json.dumps({"error": "from_unit and to_unit are required"}, ensure_ascii=False)

        temperature_units = {"celsius", "fahrenheit", "kelvin"}
        try:
            if from_unit in temperature_units or to_unit in temperature_units:
                if from_unit not in temperature_units or to_unit not in temperature_units:
                    raise ValueError("cannot convert temperature with non-temperature unit")
                converted = _convert_temperature(value, from_unit, to_unit)
                category = "temperature"
            elif from_unit in LENGTH_TO_METER and to_unit in LENGTH_TO_METER:
                base_value = value * LENGTH_TO_METER[from_unit]
                converted = base_value / LENGTH_TO_METER[to_unit]
                category = "length"
            elif from_unit in WEIGHT_TO_GRAM and to_unit in WEIGHT_TO_GRAM:
                base_value = value * WEIGHT_TO_GRAM[from_unit]
                converted = base_value / WEIGHT_TO_GRAM[to_unit]
                category = "weight"
            else:
                raise ValueError(f"unsupported conversion: {from_unit} -> {to_unit}")

            return json.dumps(
                {
                    "value": value,
                    "from_unit": from_unit,
                    "to_unit": to_unit,
                    "converted_value": round(converted, 10),
                    "category": category,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "error": str(exc),
                    "value": value,
                    "from_unit": from_unit,
                    "to_unit": to_unit,
                },
                ensure_ascii=False,
            )

    if tool_name == "get_calendar_info":
        timezone_name = str(arguments.get("timezone") or "Asia/Shanghai").strip()
        raw_date = str(arguments.get("date") or "").strip()
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            return json.dumps({"error": f"invalid timezone: {timezone_name}"}, ensure_ascii=False)

        try:
            if raw_date:
                target_date = datetime.fromisoformat(raw_date).date()
            else:
                target_date = datetime.now(tz).date()
        except Exception:
            return json.dumps(
                {"error": "date must be ISO format like YYYY-MM-DD", "date": raw_date},
                ensure_ascii=False,
            )

        iso_year, iso_week, iso_weekday = target_date.isocalendar()
        weekday_names = {
            1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
            7: "Sunday",
        }
        return json.dumps(
            {
                "date": target_date.isoformat(),
                "timezone": timezone_name,
                "weekday_index": iso_weekday,
                "weekday_name": weekday_names[iso_weekday],
                "iso_week": iso_week,
                "iso_year": iso_year,
                "is_weekend": iso_weekday in {6, 7},
            },
            ensure_ascii=False,
        )

    if tool_name == "text_stats":
        text = str(arguments.get("text") or "")
        if not text:
            return json.dumps({"error": "text is required"}, ensure_ascii=False)

        lines = text.splitlines() or [text]
        words = re.findall(r"[A-Za-z0-9_]+", text)
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        return json.dumps(
            {
                "characters": len(text),
                "characters_no_spaces": len(re.sub(r"\s+", "", text)),
                "lines": len(lines),
                "words": len(words),
                "chinese_characters": len(chinese_chars),
            },
            ensure_ascii=False,
        )

    if tool_name == "generate_uuid":
        version = int(arguments.get("version") or 4)
        if version != 4:
            return json.dumps({"error": "only version=4 is supported"}, ensure_ascii=False)
        return json.dumps({"uuid": str(uuid.uuid4()), "version": 4}, ensure_ascii=False)

    if tool_name == "random_number":
        try:
            lower = int(arguments.get("min") if arguments.get("min") is not None else 1)
            upper = int(arguments.get("max") if arguments.get("max") is not None else 100)
        except Exception:
            return json.dumps({"error": "min/max must be integers"}, ensure_ascii=False)
        if lower > upper:
            lower, upper = upper, lower
        return json.dumps(
            {"min": lower, "max": upper, "value": random.randint(lower, upper)},
            ensure_ascii=False,
        )

    if tool_name == "coin_flip":
        try:
            count = int(arguments.get("count") if arguments.get("count") is not None else 1)
        except Exception:
            return json.dumps({"error": "count must be an integer"}, ensure_ascii=False)
        count = max(1, min(count, 100))
        flips = [secrets.choice(["heads", "tails"]) for _ in range(count)]
        return json.dumps(
            {
                "count": count,
                "results": flips,
                "heads": sum(1 for item in flips if item == "heads"),
                "tails": sum(1 for item in flips if item == "tails"),
            },
            ensure_ascii=False,
        )

    if tool_name == "roll_dice":
        try:
            sides = int(arguments.get("sides") if arguments.get("sides") is not None else 6)
            count = int(arguments.get("count") if arguments.get("count") is not None else 1)
        except Exception:
            return json.dumps({"error": "sides/count must be integers"}, ensure_ascii=False)
        sides = max(2, min(sides, 1000))
        count = max(1, min(count, 100))
        results = [secrets.randbelow(sides) + 1 for _ in range(count)]
        return json.dumps(
            {"sides": sides, "count": count, "results": results, "total": sum(results)},
            ensure_ascii=False,
        )

    if tool_name == "generate_password":
        try:
            length = int(arguments.get("length") if arguments.get("length") is not None else 16)
        except Exception:
            return json.dumps({"error": "length must be an integer"}, ensure_ascii=False)
        include_symbols = bool(arguments.get("include_symbols", True))
        length = max(8, min(length, 128))
        alphabet = string.ascii_letters + string.digits
        if include_symbols:
            alphabet += "!@#$%^&*()-_=+[]{};:,.?"
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        return json.dumps(
            {
                "length": length,
                "include_symbols": include_symbols,
                "password": password,
            },
            ensure_ascii=False,
        )

    if tool_name == "hash_text":
        text = str(arguments.get("text") or "")
        if not text:
            return json.dumps({"error": "text is required"}, ensure_ascii=False)
        algorithm = str(arguments.get("algorithm") or "sha256").strip().lower()
        if algorithm not in {"md5", "sha1", "sha256", "sha512"}:
            return json.dumps({"error": "algorithm must be one of md5/sha1/sha256/sha512"}, ensure_ascii=False)
        digest = hashlib.new(algorithm, text.encode("utf-8")).hexdigest()
        return json.dumps({"algorithm": algorithm, "hash": digest}, ensure_ascii=False)

    if tool_name == "base64_codec":
        mode = str(arguments.get("mode") or "").strip().lower()
        text = str(arguments.get("text") or "")
        if mode not in {"encode", "decode"}:
            return json.dumps({"error": "mode must be encode or decode"}, ensure_ascii=False)
        try:
            if mode == "encode":
                output = base64.b64encode(text.encode("utf-8")).decode("utf-8")
            else:
                output = base64.b64decode(text.encode("utf-8"), validate=True).decode("utf-8")
            return json.dumps({"mode": mode, "output": output}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": f"base64 {mode} failed: {exc}"}, ensure_ascii=False)

    if tool_name == "get_weather":
        location = str(arguments.get("location") or "").strip()
        unit = str(arguments.get("unit") or "celsius").strip().lower()
        if unit not in {"celsius", "fahrenheit"}:
            unit = "celsius"
        if not location:
            return json.dumps({"error": "location is required"}, ensure_ascii=False)
        if not settings.WEATHER_TOOL_ENABLED:
            return json.dumps(
                {"error": "weather tool disabled by WEATHER_TOOL_ENABLED=false"},
                ensure_ascii=False,
            )

        try:
            import httpx

            timeout = httpx.Timeout(
                timeout=settings.WEATHER_TOOL_TIMEOUT_SECONDS,
                connect=min(8.0, settings.WEATHER_TOOL_TIMEOUT_SECONDS),
            )
            with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                location_candidates = _build_weather_location_candidates(location)
                best = None
                selected_query = ""

                for query in location_candidates:
                    geo = client.get(
                        "https://geocoding-api.open-meteo.com/v1/search",
                        params={
                            "name": query,
                            "count": 8,
                            "language": "en",
                            "format": "json",
                        },
                    )
                    geo.raise_for_status()
                    geo_data = geo.json()
                    results = geo_data.get("results") or []
                    if not results:
                        continue

                    # For Chinese input, prefer China candidates to reduce homonym mismatch.
                    if _is_chinese_text(location):
                        cn_results = [
                            item
                            for item in results
                            if isinstance(item, dict) and str(item.get("country_code") or "").upper() == "CN"
                        ]
                    else:
                        cn_results = []

                    pool = cn_results or [item for item in results if isinstance(item, dict)]
                    if not pool:
                        continue

                    def _rank(item: dict) -> tuple[float, float]:
                        feature = str(item.get("feature_code") or "")
                        feature_score = {
                            "PPLC": 5.0,
                            "PPLA": 4.0,
                            "PPLA2": 3.0,
                            "PPLA3": 2.0,
                            "PPLA4": 2.0,
                            "PPL": 1.0,
                        }.get(feature, 0.0)
                        pop = float(item.get("population") or 0.0)
                        return feature_score, pop

                    current_best = sorted(pool, key=_rank, reverse=True)[0]
                    best = current_best
                    selected_query = query
                    break

                if not best:
                    return json.dumps(
                        {"error": f"location not found: {location}"},
                        ensure_ascii=False,
                    )

                latitude = float(best.get("latitude"))
                longitude = float(best.get("longitude"))
                resolved_name = str(best.get("name") or location)
                country = str(best.get("country") or "")
                timezone_name = str(best.get("timezone") or "auto")

                weather = client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current": "temperature_2m,wind_speed_10m,weather_code",
                        "temperature_unit": "fahrenheit" if unit == "fahrenheit" else "celsius",
                        "wind_speed_unit": "kmh",
                        "timezone": "auto",
                    },
                )
                weather.raise_for_status()
                weather_data = weather.json()
                current = weather_data.get("current") or {}
                return json.dumps(
                    {
                        "location_query": location,
                        "location_query_resolved": selected_query or location,
                        "location": resolved_name,
                        "country": country,
                        "timezone": timezone_name,
                        "unit": unit,
                        "temperature": current.get("temperature_2m"),
                        "wind_speed_kmh": current.get("wind_speed_10m"),
                        "weather_code": current.get("weather_code"),
                        "source": "open-meteo.com",
                    },
                    ensure_ascii=False,
                )
        except Exception as exc:
            return json.dumps(
                {"error": f"get_weather failed: {exc}", "location_query": location},
                ensure_ascii=False,
            )

    if tool_name == "calculate_wind_chill":
        unit = str(arguments.get("unit") or "celsius").strip().lower()
        if unit not in {"celsius", "fahrenheit"}:
            unit = "celsius"
        try:
            temperature = float(arguments.get("temperature"))
            wind_speed_kmh = float(arguments.get("wind_speed_kmh"))
        except Exception:
            return json.dumps(
                {"error": "temperature and wind_speed_kmh must be numbers"},
                ensure_ascii=False,
            )

        if wind_speed_kmh <= 0:
            return json.dumps(
                {
                    "temperature": temperature,
                    "wind_speed_kmh": wind_speed_kmh,
                    "unit": unit,
                    "wind_chill": temperature,
                    "note": "non-positive wind speed, wind chill equals air temperature",
                },
                ensure_ascii=False,
            )

        if unit == "fahrenheit":
            wind_mph = wind_speed_kmh / 1.609344
            wind_chill = 35.74 + 0.6215 * temperature - 35.75 * math.pow(wind_mph, 0.16) + 0.4275 * temperature * math.pow(wind_mph, 0.16)
        else:
            wind_chill = 13.12 + 0.6215 * temperature - 11.37 * math.pow(wind_speed_kmh, 0.16) + 0.3965 * temperature * math.pow(wind_speed_kmh, 0.16)

        return json.dumps(
            {
                "temperature": temperature,
                "wind_speed_kmh": wind_speed_kmh,
                "unit": unit,
                "wind_chill": round(wind_chill, 2),
            },
            ensure_ascii=False,
        )

    if tool_name == "math_calculator":
        expression = str(arguments.get("expression") or "").strip()
        if not expression:
            return json.dumps({"error": "expression is required"}, ensure_ascii=False)
        try:
            value = _safe_eval_math(expression)
            return json.dumps({"expression": expression, "result": value}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"expression": expression, "error": str(exc)}, ensure_ascii=False)

    if tool_name == "search_web_realtime":
        query = str(arguments.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)

        limit = _parse_limited_int(arguments.get("limit"), default=5, minimum=1, maximum=10)
        market, language = _resolve_news_locale(
            arguments.get("market"),
            arguments.get("language"),
        )
        freshness = arguments.get("freshness")

        try:
            payload = _search_bing_news_realtime(
                query=query,
                limit=limit,
                freshness=freshness,
                market=market,
                language=language,
            )
            payload["tool"] = "search_web_realtime"
            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            return json.dumps(
                {
                    "error": f"search_web_realtime failed: {exc}",
                    "query": query,
                    "market": market,
                    "language": language,
                },
                ensure_ascii=False,
            )

    if tool_name == "search_news":
        query = str(arguments.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)

        limit = _parse_limited_int(arguments.get("limit"), default=5, minimum=1, maximum=10)
        market, language = _resolve_news_locale(
            arguments.get("market"),
            arguments.get("language"),
        )
        freshness = arguments.get("freshness")

        realtime_exc_msg = ""
        try:
            payload = _search_bing_news_realtime(
                query=query,
                limit=limit,
                freshness=freshness,
                market=market,
                language=language,
            )
            payload["tool"] = "search_news"
            payload["provider"] = "bing_news_rss"
            return json.dumps(
                payload,
                ensure_ascii=False,
            )
        except Exception as exc:
            realtime_exc_msg = str(exc)

        try:
            fallback_payload = _search_hn_news_fallback(query=query, limit=limit)
            fallback_payload["tool"] = "search_news"
            fallback_payload["provider"] = "hn_algolia_fallback"
            fallback_payload["note"] = (
                "Realtime provider unavailable, returned HN fallback results."
            )
            fallback_payload["provider_error"] = realtime_exc_msg
            return json.dumps(fallback_payload, ensure_ascii=False)
        except Exception as fallback_exc:
            return json.dumps(
                {
                    "error": f"search_news failed: realtime={realtime_exc_msg} fallback={fallback_exc}",
                    "query": query,
                    "market": market,
                    "language": language,
                },
                ensure_ascii=False,
            )

    if tool_name == "get_exchange_rate":
        base_currency = str(arguments.get("base_currency") or "").strip().upper()
        target_currency = str(arguments.get("target_currency") or "").strip().upper()
        if not base_currency or not target_currency:
            return json.dumps(
                {"error": "base_currency and target_currency are required"},
                ensure_ascii=False,
            )
        try:
            amount = float(arguments.get("amount")) if arguments.get("amount") is not None else None
        except Exception:
            return json.dumps({"error": "amount must be a number"}, ensure_ascii=False)

        try:
            import httpx

            timeout = httpx.Timeout(
                timeout=settings.WEATHER_TOOL_TIMEOUT_SECONDS,
                connect=min(8.0, settings.WEATHER_TOOL_TIMEOUT_SECONDS),
            )

            provider_errors: list[str] = []
            provider_attempts = [
                {
                    "name": "open.er-api.com",
                    "url": f"https://open.er-api.com/v6/latest/{base_currency}",
                    "parser": "er_api",
                },
                {
                    "name": "api.frankfurter.app",
                    "url": "https://api.frankfurter.app/latest",
                    "params": {"from": base_currency, "to": target_currency},
                    "parser": "frankfurter",
                },
            ]

            with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                for provider in provider_attempts:
                    source_name = str(provider["name"])
                    req_url = str(provider["url"])
                    req_params = provider.get("params")
                    last_exc: Exception | None = None

                    # Retry once for transient TLS/EOF errors.
                    for attempt in range(2):
                        try:
                            response = client.get(req_url, params=req_params)
                            response.raise_for_status()
                            payload = response.json()

                            if provider["parser"] == "er_api":
                                rates = payload.get("rates") or {}
                                rate = rates.get(target_currency)
                                if rate is None:
                                    raise ValueError(f"target currency not found: {target_currency}")
                                last_update_unix = payload.get("time_last_update_unix")
                                next_update_unix = payload.get("time_next_update_unix")
                            else:
                                rates = payload.get("rates") or {}
                                rate = rates.get(target_currency)
                                if rate is None:
                                    raise ValueError(f"target currency not found: {target_currency}")
                                last_update_unix = None
                                next_update_unix = None

                            converted = amount * float(rate) if amount is not None else None
                            return json.dumps(
                                {
                                    "base_currency": base_currency,
                                    "target_currency": target_currency,
                                    "rate": float(rate),
                                    "amount": amount,
                                    "converted_amount": round(converted, 6) if converted is not None else None,
                                    "last_update_unix": last_update_unix,
                                    "next_update_unix": next_update_unix,
                                    "source": source_name,
                                },
                                ensure_ascii=False,
                            )
                        except Exception as exc:
                            last_exc = exc
                            if attempt == 0:
                                time.sleep(0.2)
                                continue
                    if last_exc is not None:
                        provider_errors.append(f"{source_name}: {last_exc}")

            return json.dumps(
                {
                    "error": "get_exchange_rate failed for all providers",
                    "base_currency": base_currency,
                    "target_currency": target_currency,
                    "providers_tried": [item["name"] for item in provider_attempts],
                    "provider_errors": provider_errors,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "error": f"get_exchange_rate failed: {exc}",
                    "base_currency": base_currency,
                    "target_currency": target_currency,
                },
                ensure_ascii=False,
            )

    if tool_name == "stock_quote":
        symbol = str(arguments.get("symbol") or "").strip().upper()
        if not symbol:
            return json.dumps({"error": "symbol is required"}, ensure_ascii=False)

        try:
            import httpx

            timeout = httpx.Timeout(
                timeout=settings.WEATHER_TOOL_TIMEOUT_SECONDS,
                connect=min(8.0, settings.WEATHER_TOOL_TIMEOUT_SECONDS),
            )

            provider_errors: list[str] = []
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                trust_env=False,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    ),
                    "Accept": "application/json,text/plain,*/*",
                },
            ) as client:
                # Provider 1: Yahoo Quote (preferred real-time-ish).
                try:
                    endpoint = "https://query1.finance.yahoo.com/v7/finance/quote"
                    response = client.get(endpoint, params={"symbols": symbol})
                    response.raise_for_status()
                    payload = response.json()

                    result_items = (((payload.get("quoteResponse") or {}).get("result")) or [])
                    if result_items:
                        item = result_items[0]
                        return json.dumps(
                            {
                                "symbol": item.get("symbol") or symbol,
                                "short_name": item.get("shortName"),
                                "long_name": item.get("longName"),
                                "market_state": item.get("marketState"),
                                "currency": item.get("currency"),
                                "exchange": item.get("fullExchangeName") or item.get("exchange"),
                                "price": item.get("regularMarketPrice"),
                                "change": item.get("regularMarketChange"),
                                "change_percent": item.get("regularMarketChangePercent"),
                                "open": item.get("regularMarketOpen"),
                                "high": item.get("regularMarketDayHigh"),
                                "low": item.get("regularMarketDayLow"),
                                "previous_close": item.get("regularMarketPreviousClose"),
                                "timestamp": item.get("regularMarketTime"),
                                "source": "query1.finance.yahoo.com",
                            },
                            ensure_ascii=False,
                        )
                    provider_errors.append("query1.finance.yahoo.com: symbol not found")
                except Exception as exc:
                    provider_errors.append(f"query1.finance.yahoo.com: {exc}")

                # Provider 2: Stooq CSV fallback (often available when Yahoo rate-limited).
                try:
                    stooq_symbol = symbol.lower()
                    if "." not in stooq_symbol:
                        stooq_symbol = f"{stooq_symbol}.us"
                    stooq_url = "https://stooq.com/q/l/"
                    stooq_resp = client.get(stooq_url, params={"s": stooq_symbol, "i": "d"})
                    stooq_resp.raise_for_status()
                    lines = [line.strip() for line in stooq_resp.text.splitlines() if line.strip()]
                    if len(lines) < 2:
                        raise ValueError("empty csv payload")
                    headers = [h.strip() for h in lines[0].split(",")]
                    values = [v.strip() for v in lines[1].split(",")]
                    if len(headers) != len(values):
                        raise ValueError("invalid csv shape")
                    row = dict(zip(headers, values))
                    if str(row.get("Close", "")).upper() in {"N/D", ""}:
                        raise ValueError("symbol not found")

                    def _to_float(value: str | None) -> float | None:
                        text = str(value or "").strip()
                        if not text or text.upper() == "N/D":
                            return None
                        return float(text)

                    return json.dumps(
                        {
                            "symbol": symbol,
                            "short_name": None,
                            "long_name": None,
                            "market_state": "UNKNOWN",
                            "currency": None,
                            "exchange": "Stooq",
                            "price": _to_float(row.get("Close")),
                            "change": None,
                            "change_percent": None,
                            "open": _to_float(row.get("Open")),
                            "high": _to_float(row.get("High")),
                            "low": _to_float(row.get("Low")),
                            "previous_close": None,
                            "timestamp": f"{row.get('Date', '')} {row.get('Time', '')}".strip() or None,
                            "source": "stooq.com",
                            "note": "Fallback source (may be delayed)",
                        },
                        ensure_ascii=False,
                    )
                except Exception as exc:
                    provider_errors.append(f"stooq.com: {exc}")

            return json.dumps(
                {
                    "error": "stock_quote failed for all providers",
                    "symbol": symbol,
                    "providers_tried": ["query1.finance.yahoo.com", "stooq.com"],
                    "provider_errors": provider_errors,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps(
                {"error": f"stock_quote failed: {exc}", "symbol": symbol},
                ensure_ascii=False,
            )

    return json.dumps({"error": f"unsupported tool: {tool_name}"}, ensure_ascii=False)


def _generate_vllm_with_modes(
    *,
    question: str,
    context: str,
    image_data: str | None,
    image_format: str | None,
    image_data_list: list[str] | None,
    image_format_list: list[str | None] | None,
    audio_url: str | None,
    audio_url_list: list[str] | None,
    video_url: str | None,
    video_url_list: list[str] | None,
    enable_thinking: bool,
    enable_tool_calling: bool,
    response_format: dict[str, Any] | None,
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Generate response for vLLM mode combinations (text/multimodal/thinking/tools)."""
    client = get_openai_client()
    user_content = _build_vllm_user_content(
        question=question,
        context=context,
        image_data=image_data,
        image_format=image_format,
        image_data_list=image_data_list,
        image_format_list=image_format_list,
        audio_url=audio_url,
        audio_url_list=audio_url_list,
        video_url=video_url,
        video_url_list=video_url_list,
    )
    messages: list[dict] = [{"role": "system", "content": settings.SYSTEM_PROMPT}]
    if enable_tool_calling:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Tool policy: for requests about latest/recent/current events or realtime web info, "
                    "call search_web_realtime (or search_news) before answering. "
                    "If tool output is empty or contains error, explicitly mention it."
                ),
            }
        )
    messages.append({"role": "user", "content": user_content})
    resolved_max_tokens, resolved_temperature, resolved_top_p = _resolve_generation_params(
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )

    extra_body = _build_extra_body(enable_thinking)

    if not enable_tool_calling:
        kwargs = {
            "model": settings.VLLM_MODEL,
            "messages": messages,
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
            "max_tokens": resolved_max_tokens,
            "stream": False,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        reasoning, answer = _extract_reasoning_and_answer(message)
        return reasoning, answer, []

    reasoning_parts: list[str] = []
    tool_traces: list[dict[str, Any]] = []
    final_answer = ""

    for _ in range(max(1, settings.MAX_TOOL_CALL_ROUNDS)):
        kwargs = {
            "model": settings.VLLM_MODEL,
            "messages": messages,
            "tools": BUILTIN_TOOLS,
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
            "max_tokens": resolved_max_tokens,
            "stream": False,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = client.chat.completions.create(**kwargs)
        assistant_message = response.choices[0].message
        reasoning, answer = _extract_reasoning_and_answer(assistant_message)
        if reasoning:
            reasoning_parts.append(reasoning.strip())
        if answer:
            final_answer = answer.strip()

        tool_calls = assistant_message.tool_calls or []
        if not tool_calls:
            break

        assistant_tool_calls = []
        for call in tool_calls:
            tool_name = call.function.name if call.function else ""
            tool_args = call.function.arguments if call.function else "{}"
            assistant_tool_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_args,
                    },
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": _extract_text_field(assistant_message.content) if hasattr(assistant_message, "content") else "",
                "tool_calls": assistant_tool_calls,
            }
        )

        for call in tool_calls:
            tool_name = call.function.name if call.function else ""
            tool_args = call.function.arguments if call.function else "{}"
            started_at = time.time()
            tool_output = _execute_builtin_tool(tool_name, tool_args)
            elapsed_ms = max(0.0, (time.time() - started_at) * 1000.0)
            tool_traces.append(
                {
                    "id": call.id,
                    "name": tool_name,
                    "arguments": tool_args,
                    "output": tool_output,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "ts": datetime.utcnow().isoformat() + "Z",
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tool_output,
                }
            )

    merged_reasoning = "\n\n".join([item for item in reasoning_parts if item]).strip()
    return merged_reasoning, final_answer, tool_traces


def generate_response_structured(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> dict[str, Any]:
    """Generate non-stream response and keep reasoning/final answer separated."""
    if settings.LLM_PROVIDER == "vllm":
        reasoning, answer, tool_traces = _generate_vllm_with_modes(
            question=question,
            context=context,
            image_data=image_data,
            image_format=image_format,
            image_data_list=image_data_list,
            image_format_list=image_format_list,
            audio_url=audio_url,
            audio_url_list=audio_url_list,
            video_url=video_url,
            video_url_list=video_url_list,
            enable_thinking=enable_thinking,
            enable_tool_calling=enable_tool_calling,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return {
            "reasoning_content": reasoning.strip(),
            "final_content": answer.strip(),
            "tool_traces": tool_traces,
        }

    answer = generate_response(
        question=question,
        context=context,
        image_data=image_data,
        image_format=image_format,
        image_data_list=image_data_list,
        image_format_list=image_format_list,
        audio_url=audio_url,
        audio_url_list=audio_url_list,
        video_url=video_url,
        video_url_list=video_url_list,
        enable_thinking=enable_thinking,
        enable_tool_calling=enable_tool_calling,
        response_format=response_format,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )
    return {
        "reasoning_content": "",
        "final_content": answer.strip(),
        "tool_traces": [],
    }


def format_prompt(question: str, context: str = "") -> str:
    """Format prompt using the configured chat template with RAG context.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Returns:
        Formatted prompt string
    """
    template_type = settings.CHAT_TEMPLATE_TYPE
    template = CHAT_TEMPLATES.get(template_type, CHAT_TEMPLATES["llama"])

    user_content = _format_user_text(question, context)

    return template.format(
        system_prompt=settings.SYSTEM_PROMPT,
        context="",  # Context is now in user_content
        question=user_content,
    )


def generate_response(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Generate a non-streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Returns:
        Generated response text
    """
    if settings.LLM_PROVIDER == "vllm":
        payload = generate_response_structured(
            question=question,
            context=context,
            image_data=image_data,
            image_format=image_format,
            image_data_list=image_data_list,
            image_format_list=image_format_list,
            audio_url=audio_url,
            audio_url_list=audio_url_list,
            video_url=video_url,
            video_url_list=video_url_list,
            enable_thinking=enable_thinking,
            enable_tool_calling=enable_tool_calling,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return _format_thinking_output(
            payload.get("reasoning_content", ""),
            payload.get("final_content", ""),
        ).strip()

    llm = get_llm()
    prompt = format_prompt(question, context)
    resolved_max_tokens, resolved_temperature, resolved_top_p = _resolve_generation_params(
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )

    output = llm(
        prompt,
        max_tokens=resolved_max_tokens,
        temperature=resolved_temperature,
        top_p=resolved_top_p,
        top_k=settings.TOP_K,
        stop=get_stop_tokens(),
        echo=False,
        repeat_penalty=1.1,  # Add repetition penalty to prevent loops
    )

    # Extract just the response part
    response_text = output["choices"][0]["text"].strip()
    return response_text


def stream_response_events(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Generate structured streaming events.

    Yields event dicts, e.g. {"type":"reasoning|answer","token":"..."} or {"type":"tool_trace","trace":{...}}.
    """
    if settings.LLM_PROVIDER == "vllm":
        resolved_max_tokens, resolved_temperature, resolved_top_p = _resolve_generation_params(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        if enable_tool_calling:
            reasoning, answer, tool_traces = _generate_vllm_with_modes(
                question=question,
                context=context,
                image_data=image_data,
                image_format=image_format,
                image_data_list=image_data_list,
                image_format_list=image_format_list,
                audio_url=audio_url,
                audio_url_list=audio_url_list,
                video_url=video_url,
                video_url_list=video_url_list,
                enable_thinking=enable_thinking,
                enable_tool_calling=True,
                response_format=response_format,
                max_tokens=resolved_max_tokens,
                temperature=resolved_temperature,
                top_p=resolved_top_p,
            )
            reasoning_text = (reasoning or "").strip()
            answer_text = (answer or "").strip()
            for idx in range(0, len(reasoning_text), 12):
                chunk = reasoning_text[idx: idx + 12]
                if chunk:
                    yield {"type": "reasoning", "token": chunk}
            for trace in tool_traces:
                yield {"type": "tool_trace", "trace": trace}
            for idx in range(0, len(answer_text), 12):
                chunk = answer_text[idx: idx + 12]
                if chunk:
                    yield {"type": "answer", "token": chunk}
            return

        logger.info(
            "Dispatching vLLM stream request: model=%s image_count=%d audio_count=%d video_count=%d thinking=%s tool_calling=%s image_chars=%d question_chars=%d context_chars=%d",
            settings.VLLM_MODEL,
            len(_collect_multimodal_images(image_data, image_format, image_data_list, image_format_list)),
            len(_collect_multimodal_audio(audio_url, audio_url_list)),
            len(_collect_multimodal_videos(video_url, video_url_list)),
            enable_thinking,
            enable_tool_calling,
            len(image_data or "") + sum(len(item or "") for item in (image_data_list or [])),
            len(question or ""),
            len(context or ""),
        )
        client = get_openai_client()
        user_content = _build_vllm_user_content(
            question=question,
            context=context,
            image_data=image_data,
            image_format=image_format,
            image_data_list=image_data_list,
            image_format_list=image_format_list,
            audio_url=audio_url,
            audio_url_list=audio_url_list,
            video_url=video_url,
            video_url_list=video_url_list,
        )
        kwargs = {
            "model": settings.VLLM_MODEL,
            "messages": [
                {"role": "system", "content": settings.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
            "max_tokens": resolved_max_tokens,
            "stream": True,
        }
        if response_format:
            kwargs["response_format"] = response_format
        extra_body = _build_extra_body(enable_thinking)
        if extra_body:
            kwargs["extra_body"] = extra_body
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta:
                continue

            reasoning_token = _extract_delta_reasoning(delta)
            answer_token = _extract_delta_answer(delta)

            if reasoning_token:
                yield {"type": "reasoning", "token": reasoning_token}

            if answer_token:
                yield {"type": "answer", "token": answer_token}
        return

    llm = get_llm()
    prompt = format_prompt(question, context)
    resolved_max_tokens, resolved_temperature, resolved_top_p = _resolve_generation_params(
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )

    for chunk in llm(
        prompt,
        max_tokens=resolved_max_tokens,
        temperature=resolved_temperature,
        top_p=resolved_top_p,
        top_k=settings.TOP_K,
        stop=get_stop_tokens(),
        echo=False,
        stream=True,
        repeat_penalty=1.1,  # Add repetition penalty to prevent loops
    ):
        if "choices" in chunk and len(chunk["choices"]) > 0:
            token = chunk["choices"][0].get("text", "")
            if token:
                yield {"type": "answer", "token": token}


def stream_response(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> Generator[str, None, None]:
    """Legacy stream API: merges reasoning + answer into one text channel."""
    reasoning_started = False
    answer_started = False
    for event in stream_response_events(
        question=question,
        context=context,
        image_data=image_data,
        image_format=image_format,
        image_data_list=image_data_list,
        image_format_list=image_format_list,
        audio_url=audio_url,
        audio_url_list=audio_url_list,
        video_url=video_url,
        video_url_list=video_url_list,
        enable_thinking=enable_thinking,
        enable_tool_calling=enable_tool_calling,
        response_format=response_format,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    ):
        event_type = event.get("type")
        token = event.get("token") or ""
        if not token:
            continue
        if event_type == "reasoning":
            if not reasoning_started:
                reasoning_started = True
                yield "thought "
            yield token
            continue
        if reasoning_started and not answer_started:
            answer_started = True
            yield "\n\nFinal answer:\n"
        yield token


async def astream_response_events(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async structured stream API."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[object] = asyncio.Queue()
    end_marker = object()

    def _produce_tokens() -> None:
        """Run blocking stream generation in a thread and forward events."""
        try:
            for event in stream_response_events(
                question=question,
                context=context,
                image_data=image_data,
                image_format=image_format,
                image_data_list=image_data_list,
                image_format_list=image_format_list,
                audio_url=audio_url,
                audio_url_list=audio_url_list,
                video_url=video_url,
                video_url_list=video_url_list,
                enable_thinking=enable_thinking,
                enable_tool_calling=enable_tool_calling,
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, end_marker)

    producer = asyncio.create_task(asyncio.to_thread(_produce_tokens))
    try:
        while True:
            item = await queue.get()
            if item is end_marker:
                break
            if isinstance(item, Exception):
                raise item
            yield dict(item)
    finally:
        await producer


async def astream_response(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
    image_data_list: list[str] | None = None,
    image_format_list: list[str | None] | None = None,
    audio_url: str | None = None,
    audio_url_list: list[str] | None = None,
    video_url: str | None = None,
    video_url_list: list[str] | None = None,
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    """Legacy async stream API: merges reasoning + answer into one text channel."""
    reasoning_started = False
    answer_started = False
    async for event in astream_response_events(
        question=question,
        context=context,
        image_data=image_data,
        image_format=image_format,
        image_data_list=image_data_list,
        image_format_list=image_format_list,
        audio_url=audio_url,
        audio_url_list=audio_url_list,
        video_url=video_url,
        video_url_list=video_url_list,
        enable_thinking=enable_thinking,
        enable_tool_calling=enable_tool_calling,
        response_format=response_format,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    ):
        event_type = event.get("type")
        token = event.get("token") or ""
        if not token:
            continue
        if event_type == "reasoning":
            if not reasoning_started:
                reasoning_started = True
                yield "thought "
            yield token
            continue
        if reasoning_started and not answer_started:
            answer_started = True
            yield "\n\nFinal answer:\n"
        yield token


def is_model_loaded() -> bool:
    """Check if the LLM model is loaded."""
    if settings.LLM_PROVIDER == "vllm":
        return True
    return _llm_instance is not None


def unload_model():
    """Unload the LLM model to free memory."""
    global _llm_instance, _openai_client, _vllm_probe_cache
    _llm_instance = None
    _openai_client = None
    _vllm_probe_cache = None
