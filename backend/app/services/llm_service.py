"""LLM Service using Llama.cpp for Mac M3 Metal acceleration.

This service wraps llama-cpp-python for optimized inference on Apple Silicon.
Supports multiple model types (Qwen, Mistral, Llama, etc.).
"""
import asyncio
from pathlib import Path
from typing import Optional, Generator, AsyncGenerator

from app.core.config import settings, MODELS_DIR

# Global LLM instance
_llm_instance: Optional["Llama"] = None

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


def get_stop_tokens() -> list[str]:
    """Get appropriate stop tokens based on model type."""
    template_type = settings.CHAT_TEMPLATE_TYPE
    if template_type == "qwen":
        # Qwen2.5 uses <|im_end|> as stop token
        return ["<|im_end|>"]
    else:  # mistral, llama
        return ["[/INST]"]


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

    # Prepare context string for RAG
    if context:
        # RAG mode: include context in prompt
        user_content = f"【参考文档】\n{context}\n\n【用户问题】\n{question}"
    else:
        # General chat mode: no context available
        user_content = question

    return template.format(
        system_prompt=settings.SYSTEM_PROMPT,
        context="",  # Context is now in user_content
        question=user_content,
    )


def generate_response(question: str, context: str = "") -> str:
    """Generate a non-streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Returns:
        Generated response text
    """
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
) -> Generator[str, None, None]:
    """Generate a streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Yields:
        Response tokens as they are generated
    """
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
) -> AsyncGenerator[str, None]:
    """Async version of streaming response.

    Args:
        question: User question
        context: Retrieved context from RAG (optional)

    Yields:
        Response tokens as they are generated
    """
    loop = asyncio.get_event_loop()

    def _stream():
        return stream_response(question, context)

    for token in await loop.run_in_executor(None, lambda: list(_stream())):
        yield token


def is_model_loaded() -> bool:
    """Check if the LLM model is loaded."""
    return _llm_instance is not None


def unload_model():
    """Unload the LLM model to free memory."""
    global _llm_instance
    _llm_instance = None
