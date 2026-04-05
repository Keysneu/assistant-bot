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
from typing import Optional, Generator, AsyncGenerator

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


def _build_vllm_user_content(
    question: str,
    context: str = "",
    image_data: str | None = None,
    image_format: str | None = None,
):
    """Build user content payload for vLLM chat completion request."""
    user_text = _format_user_text(question, context)
    if not image_data:
        return user_text

    return [
        {"type": "text", "text": user_text},
        {
            "type": "image_url",
            "image_url": {"url": _build_data_url_image(image_data, image_format)},
        },
    ]


def _build_extra_body(enable_thinking: bool) -> dict | None:
    """Build extra body fields for Gemma4 optional modes."""
    if not enable_thinking:
        return None
    return {
        "chat_template_kwargs": {
            "enable_thinking": True,
        }
    }


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
    enable_thinking: bool,
    enable_tool_calling: bool,
) -> str:
    """Generate response for vLLM mode combinations (text/multimodal/thinking/tools)."""
    client = get_openai_client()
    user_content = _build_vllm_user_content(
        question=question,
        context=context,
        image_data=image_data,
        image_format=image_format,
    )
    messages: list[dict] = [
        {"role": "system", "content": settings.SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    extra_body = _build_extra_body(enable_thinking)

    if not enable_tool_calling:
        kwargs = {
            "model": settings.VLLM_MODEL,
            "messages": messages,
            "temperature": settings.TEMPERATURE,
            "top_p": settings.TOP_P,
            "max_tokens": settings.MAX_TOKENS,
            "stream": False,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()

    first_kwargs = {
        "model": settings.VLLM_MODEL,
        "messages": messages,
        "tools": BUILTIN_TOOLS,
        "temperature": settings.TEMPERATURE,
        "top_p": settings.TOP_P,
        "max_tokens": settings.MAX_TOKENS,
        "stream": False,
    }
    if extra_body:
        first_kwargs["extra_body"] = extra_body
    first_response = client.chat.completions.create(**first_kwargs)
    first_message = first_response.choices[0].message
    tool_calls = first_message.tool_calls or []

    if not tool_calls:
        return (first_message.content or "").strip()

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
        "temperature": settings.TEMPERATURE,
        "top_p": settings.TOP_P,
        "max_tokens": settings.MAX_TOKENS,
        "stream": False,
    }
    if extra_body:
        second_kwargs["extra_body"] = extra_body
    second_response = client.chat.completions.create(**second_kwargs)
    return (second_response.choices[0].message.content or "").strip()


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
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
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
            enable_thinking=enable_thinking,
            enable_tool_calling=enable_tool_calling,
        )

    llm = get_llm()
    prompt = format_prompt(question, context)

    output = llm(
        prompt,
        max_tokens=settings.MAX_TOKENS,
        temperature=settings.TEMPERATURE,
        top_p=settings.TOP_P,
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
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
) -> Generator[str, None, None]:
    """Generate a streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Yields:
        Response tokens as they are generated
    """
    if settings.LLM_PROVIDER == "vllm":
        if enable_tool_calling:
            text = _generate_vllm_with_modes(
                question=question,
                context=context,
                image_data=image_data,
                image_format=image_format,
                enable_thinking=enable_thinking,
                enable_tool_calling=True,
            )
            # Tool-calling path uses non-stream completion then chunk output.
            for idx in range(0, len(text), 12):
                chunk = text[idx: idx + 12]
                if chunk:
                    yield chunk
            return

        logger.info(
            "Dispatching vLLM stream request: model=%s has_image=%s thinking=%s tool_calling=%s image_chars=%d question_chars=%d context_chars=%d",
            settings.VLLM_MODEL,
            bool(image_data),
            enable_thinking,
            enable_tool_calling,
            len(image_data or ""),
            len(question or ""),
            len(context or ""),
        )
        client = get_openai_client()
        user_content = _build_vllm_user_content(
            question=question,
            context=context,
            image_data=image_data,
            image_format=image_format,
        )
        kwargs = {
            "model": settings.VLLM_MODEL,
            "messages": [
                {"role": "system", "content": settings.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": settings.TEMPERATURE,
            "top_p": settings.TOP_P,
            "max_tokens": settings.MAX_TOKENS,
            "stream": True,
        }
        extra_body = _build_extra_body(enable_thinking)
        if extra_body:
            kwargs["extra_body"] = extra_body
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            token = delta.content if delta else None
            if token:
                yield token
        return

    llm = get_llm()
    prompt = format_prompt(question, context)

    for chunk in llm(
        prompt,
        max_tokens=settings.MAX_TOKENS,
        temperature=settings.TEMPERATURE,
        top_p=settings.TOP_P,
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
    enable_thinking: bool = False,
    enable_tool_calling: bool = False,
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
                enable_thinking=enable_thinking,
                enable_tool_calling=enable_tool_calling,
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
