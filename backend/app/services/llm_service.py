"""LLM Service using Llama.cpp for Mac M3 Metal acceleration.

This service wraps llama-cpp-python for optimized inference on Apple Silicon.
Supports multiple model types (Qwen, Mistral, Llama, etc.).
"""
import asyncio
import ast
import json
import logging
import operator
import time
from datetime import datetime
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
            "description": "Get current server time in ISO format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "Optional timezone hint"},
                },
                "required": [],
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
        now_iso = datetime.utcnow().isoformat() + "Z"
        return json.dumps({"current_time_utc": now_iso, "timezone_hint": tz}, ensure_ascii=False)

    if tool_name == "math_calculator":
        expression = str(arguments.get("expression") or "").strip()
        if not expression:
            return json.dumps({"error": "expression is required"}, ensure_ascii=False)
        try:
            value = _safe_eval_math(expression)
            return json.dumps({"expression": expression, "result": value}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"expression": expression, "error": str(exc)}, ensure_ascii=False)

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
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
) -> str:
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
    messages: list[dict] = [
        {"role": "system", "content": settings.SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
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
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        reasoning, answer = _extract_reasoning_and_answer(message)
        formatted = _format_thinking_output(reasoning, answer).strip()
        return formatted

    first_kwargs = {
        "model": settings.VLLM_MODEL,
        "messages": messages,
        "tools": BUILTIN_TOOLS,
        "temperature": resolved_temperature,
        "top_p": resolved_top_p,
        "max_tokens": resolved_max_tokens,
        "stream": False,
    }
    if extra_body:
        first_kwargs["extra_body"] = extra_body
    first_response = client.chat.completions.create(**first_kwargs)
    first_message = first_response.choices[0].message
    tool_calls = first_message.tool_calls or []

    if not tool_calls:
        reasoning, answer = _extract_reasoning_and_answer(first_message)
        return _format_thinking_output(reasoning, answer).strip()

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
            "content": first_message.content or "",
            "tool_calls": assistant_tool_calls,
        }
    )

    for call in tool_calls:
        tool_name = call.function.name if call.function else ""
        tool_args = call.function.arguments if call.function else "{}"
        tool_output = _execute_builtin_tool(tool_name, tool_args)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_output,
            }
        )

    second_kwargs = {
        "model": settings.VLLM_MODEL,
        "messages": messages,
        "tools": BUILTIN_TOOLS,
        "temperature": resolved_temperature,
        "top_p": resolved_top_p,
        "max_tokens": resolved_max_tokens,
        "stream": False,
    }
    if extra_body:
        second_kwargs["extra_body"] = extra_body
    second_response = client.chat.completions.create(**second_kwargs)
    second_message = second_response.choices[0].message
    reasoning, answer = _extract_reasoning_and_answer(second_message)
    return _format_thinking_output(reasoning, answer).strip()


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
        return _generate_vllm_with_modes(
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
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )

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
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> Generator[str, None, None]:
    """Generate a streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Yields:
        Response tokens as they are generated
    """
    if settings.LLM_PROVIDER == "vllm":
        resolved_max_tokens, resolved_temperature, resolved_top_p = _resolve_generation_params(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        if enable_tool_calling:
            text = _generate_vllm_with_modes(
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
                max_tokens=resolved_max_tokens,
                temperature=resolved_temperature,
                top_p=resolved_top_p,
            )
            # Tool-calling path uses non-stream completion then chunk output.
            for idx in range(0, len(text), 12):
                chunk = text[idx: idx + 12]
                if chunk:
                    yield chunk
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
        extra_body = _build_extra_body(enable_thinking)
        if extra_body:
            kwargs["extra_body"] = extra_body
        stream = client.chat.completions.create(**kwargs)
        reasoning_started = False
        answer_started = False
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta:
                continue

            reasoning_token = _extract_delta_reasoning(delta)
            answer_token = _extract_delta_answer(delta)

            if reasoning_token:
                if not reasoning_started:
                    reasoning_started = True
                    yield "thought "
                yield reasoning_token

            if answer_token:
                if reasoning_started and not answer_started:
                    answer_started = True
                    yield "\n\nFinal answer:\n"
                yield answer_token
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
                yield token


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
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> AsyncGenerator[str, None]:
    """Async version of streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Yields:
        Response tokens as they are generated
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[object] = asyncio.Queue()
    end_marker = object()

    def _produce_tokens() -> None:
        """Run blocking stream generation in a thread and forward tokens to async loop."""
        try:
            for token in stream_response(
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
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, token)
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
            yield str(item)
    finally:
        await producer


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
