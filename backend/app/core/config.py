"""AssistantBot Core Configuration

Mac M3 optimized settings for Metal acceleration.
"""
from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        # Always resolve env from backend/.env regardless of launch cwd.
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        case_sensitive=True,
    )

    # API Settings
    API_V1_PREFIX: str = "/api"
    PROJECT_NAME: str = "AssistantBot"
    VERSION: str = "0.1.0"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # LLM Settings (Qwen2.5-7B GGUF - much smarter model)
    LLM_PROVIDER: str = "llama_cpp"  # llama_cpp | vllm
    MODEL_PATH: str = "./models/qwen2.5-7b-instruct-q3_k_m.gguf"
    N_GPU_LAYERS: int = -1  # -1 = offload all layers to Metal GPU
    N_CTX: int = 4096  # Context window size
    F16_KV: bool = True  # Use half-precision for KV cache
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 8192
    MAX_TOKENS_HARD_LIMIT: int = 16384  # Upper bound for per-request max_tokens override
    TOP_P: float = 0.95
    TOP_K: int = 40

    # Chat template type (qwen, mistral, llama, etc.)
    CHAT_TEMPLATE_TYPE: str = "qwen"

    # vLLM Server Settings (OpenAI-compatible endpoint)
    VLLM_BASE_URL: str = "http://127.0.0.1:8100/v1"
    VLLM_API_KEY: str = "EMPTY"
    VLLM_MODEL: str = "gemma4-e4b-it"
    VLLM_DEPLOY_PROFILE: str = "full_featured"  # rag_text | vision | full | full_featured | benchmark | extreme
    VLLM_TIMEOUT_SECONDS: float = 600.0
    VLLM_PROBE_TIMEOUT_SECONDS: float = 8.0
    VLLM_HEALTH_CACHE_SECONDS: float = 5.0

    # Multimodal safety guard (base64 chars, without data URL prefix)
    MAX_IMAGE_BASE64_CHARS: int = 50_000_000
    MAX_SESSION_IMAGE_BASE64_CHARS: int = 5_000_000
    MAX_CHAT_FILE_BASE64_CHARS: int = 80_000_000
    MAX_CHAT_FILE_CONTEXT_CHARS: int = 500_000
    CHAT_FILE_ALLOWED_EXTENSIONS: str = ".txt,.md,.markdown,.pdf,.csv,.json,.log"
    MAX_CHAT_IMAGE_UPLOAD_MB: int = 64
    CHAT_IMAGE_CACHE_DIR: str = "./data/chat_images"
    CHAT_IMAGE_CACHE_TTL_SECONDS: int = 604_800
    CHAT_IMAGE_CACHE_MAX_FILES: int = 20_000
    CHAT_IMAGE_TARGET_MAX_EDGE: int = 4096
    CHAT_IMAGE_TARGET_MAX_BYTES: int = 8_000_000
    CHAT_IMAGE_TARGET_QUALITY: int = 95
    MAX_CHAT_AUDIO_UPLOAD_MB: int = 32
    CHAT_AUDIO_CACHE_DIR: str = "./data/chat_audios"
    CHAT_AUDIO_CACHE_TTL_SECONDS: int = 604_800
    CHAT_AUDIO_CACHE_MAX_FILES: int = 20_000
    CHAT_AUDIO_ALLOWED_EXTENSIONS: str = ".wav,.mp3,.ogg,.webm,.m4a,.mp4,.flac"
    ALLOW_PUBLIC_AUDIO_URLS: bool = False
    AUDIO_FETCH_TIMEOUT_SECONDS: float = 20.0
    MAX_AUDIO_FETCH_BYTES: int = 25_000_000
    MAX_CHAT_VIDEO_UPLOAD_MB: int = 256
    CHAT_VIDEO_CACHE_DIR: str = "./data/chat_videos"
    CHAT_VIDEO_CACHE_TTL_SECONDS: int = 604_800
    CHAT_VIDEO_CACHE_MAX_FILES: int = 10_000
    CHAT_VIDEO_ALLOWED_EXTENSIONS: str = ".mp4,.mov,.webm,.mkv,.m4v,.avi"
    ALLOW_PUBLIC_VIDEO_URLS: bool = False
    # Must be reachable by the vLLM server when backend passes local /api/chat/videos/{video_id}.
    LOCAL_MEDIA_BASE_URL: str = "http://127.0.0.1:8000"
    # Preferred transport for local uploaded video when sending to vLLM.
    # data_url: avoid vLLM reverse-fetch dependency; url: let vLLM pull by URL.
    LOCAL_VIDEO_TRANSPORT_MODE: str = "data_url"  # data_url | url
    MAX_VIDEO_DATA_URL_BYTES: int = 50_000_000

    # Document upload limits
    MAX_UPLOAD_FILE_SIZE_MB: int = 200
    MAX_BATCH_UPLOAD_FILES: int = 100
    UPLOAD_ALLOWED_EXTENSIONS: str = ".txt,.md,.markdown,.html,.htm,.pdf"

    # Embedding Settings (GTE-large with MPS)
    EMBEDDING_MODEL: str = "thenlper/gte-large"
    EMBEDDING_DEVICE: str = "mps"  # Apple Silicon Neural Engine

    # Vision Model Settings
    # Choice: "glm" for GLM-4V API (recommended, no local model), "local" for BLIP-2
    VISION_BACKEND: str = "glm"  # "glm" or "local"
    DISABLE_GLM_VISION: bool = False  # Force disable GLM vision path (recommended when using Gemma4 native multimodal)

    # GLM-4V API Settings (智谱 AI)
    GLM_API_KEY: str = ""  # 智谱 AI API Key
    GLM_VISION_MODEL: str = "glm-4v-flash"  # glm-4v-flash (免费), glm-4v (付费), glm-4v-plus (高级)

    # Local BLIP-2 Settings (fallback, ~15GB download)
    VISION_MODEL: str = "Salesforce/blip2-opt-2.7b"
    VISION_DEVICE: str = "mps"  # Apple Silicon Neural Engine
    VISION_MAX_LENGTH: int = 50  # Max caption length

    # ChromaDB Settings
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    COLLECTION_NAME: str = "documents"

    # RAG Settings - Optimized for better document understanding
    CHUNK_SIZE: int = 800  # Larger chunks for better context understanding
    CHUNK_OVERLAP: int = 200  # More overlap to preserve context continuity
    RETRIEVAL_K: int = 4  # Number of chunks to retrieve
    MIN_RELEVANCE_SCORE: float = 0.20  # Minimum relevance threshold
    RERANK_TOP_K: int = 3  # Re-rank top results for final answer

    # External APIs
    METAPHOR_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Prompt Template (Qwen2.5 format - Hybrid RAG + Free Chat mode)
    # 混合模式：优先使用知识库，没有则自由回答
    SYSTEM_PROMPT: str = """你是一个名为 AssistantBot 的智能 AI 助手。

【回答策略 - 混合模式】
1. 如果【参考文档】中包含相关信息，请优先基于文档内容回答
2. 如果【参考文档】为空或没有相关信息，请用自己的知识回答问题
3. 对于文档中的事实信息，可以适当引用来源
4. 保持回答准确、有用、友好

【回答格式】
- 有文档时：基于文档回答，可说明"根据文档..."
- 无文档时：正常回答，作为智能助手提供帮助
- 保持简洁但完整的回答"""

    MISTRAL_TEMPLATE: str = """[INST] <<SYS>>
{system_prompt}
<</SYS>>

{context}

{question} [/INST]"""

    @model_validator(mode="after")
    def validate_provider_settings(self) -> "Settings":
        """Fail fast on invalid provider configuration."""
        if self.LLM_PROVIDER not in {"llama_cpp", "vllm"}:
            raise ValueError("LLM_PROVIDER must be 'llama_cpp' or 'vllm'")

        if self.LLM_PROVIDER == "vllm":
            if not self.VLLM_API_KEY.strip():
                raise ValueError("VLLM_API_KEY is required when LLM_PROVIDER=vllm")
            if not self.VLLM_BASE_URL.startswith(("http://", "https://")):
                raise ValueError("VLLM_BASE_URL must start with http:// or https://")
            if self.VLLM_DEPLOY_PROFILE not in {"rag_text", "vision", "full", "full_featured", "benchmark", "extreme"}:
                raise ValueError(
                    "VLLM_DEPLOY_PROFILE must be one of: rag_text, vision, full, full_featured, benchmark, extreme"
                )

        if self.MAX_TOKENS <= 0:
            raise ValueError("MAX_TOKENS must be > 0")
        if self.MAX_TOKENS_HARD_LIMIT < self.MAX_TOKENS:
            raise ValueError("MAX_TOKENS_HARD_LIMIT must be >= MAX_TOKENS")

        if self.MAX_UPLOAD_FILE_SIZE_MB <= 0:
            raise ValueError("MAX_UPLOAD_FILE_SIZE_MB must be > 0")
        if self.MAX_BATCH_UPLOAD_FILES <= 0:
            raise ValueError("MAX_BATCH_UPLOAD_FILES must be > 0")
        if self.MAX_CHAT_FILE_BASE64_CHARS <= 0:
            raise ValueError("MAX_CHAT_FILE_BASE64_CHARS must be > 0")
        if self.MAX_SESSION_IMAGE_BASE64_CHARS <= 0:
            raise ValueError("MAX_SESSION_IMAGE_BASE64_CHARS must be > 0")
        if self.MAX_CHAT_FILE_CONTEXT_CHARS <= 0:
            raise ValueError("MAX_CHAT_FILE_CONTEXT_CHARS must be > 0")
        if self.MAX_CHAT_IMAGE_UPLOAD_MB <= 0:
            raise ValueError("MAX_CHAT_IMAGE_UPLOAD_MB must be > 0")
        if self.CHAT_IMAGE_CACHE_TTL_SECONDS <= 0:
            raise ValueError("CHAT_IMAGE_CACHE_TTL_SECONDS must be > 0")
        if self.CHAT_IMAGE_CACHE_MAX_FILES <= 0:
            raise ValueError("CHAT_IMAGE_CACHE_MAX_FILES must be > 0")
        if self.CHAT_IMAGE_TARGET_MAX_EDGE <= 0:
            raise ValueError("CHAT_IMAGE_TARGET_MAX_EDGE must be > 0")
        if self.CHAT_IMAGE_TARGET_MAX_BYTES <= 0:
            raise ValueError("CHAT_IMAGE_TARGET_MAX_BYTES must be > 0")
        if self.CHAT_IMAGE_TARGET_QUALITY <= 0 or self.CHAT_IMAGE_TARGET_QUALITY > 95:
            raise ValueError("CHAT_IMAGE_TARGET_QUALITY must be in (0, 95]")
        if self.MAX_CHAT_AUDIO_UPLOAD_MB <= 0:
            raise ValueError("MAX_CHAT_AUDIO_UPLOAD_MB must be > 0")
        if self.CHAT_AUDIO_CACHE_TTL_SECONDS <= 0:
            raise ValueError("CHAT_AUDIO_CACHE_TTL_SECONDS must be > 0")
        if self.CHAT_AUDIO_CACHE_MAX_FILES <= 0:
            raise ValueError("CHAT_AUDIO_CACHE_MAX_FILES must be > 0")
        if self.AUDIO_FETCH_TIMEOUT_SECONDS <= 0:
            raise ValueError("AUDIO_FETCH_TIMEOUT_SECONDS must be > 0")
        if self.MAX_AUDIO_FETCH_BYTES <= 0:
            raise ValueError("MAX_AUDIO_FETCH_BYTES must be > 0")
        if self.MAX_CHAT_VIDEO_UPLOAD_MB <= 0:
            raise ValueError("MAX_CHAT_VIDEO_UPLOAD_MB must be > 0")
        if self.CHAT_VIDEO_CACHE_TTL_SECONDS <= 0:
            raise ValueError("CHAT_VIDEO_CACHE_TTL_SECONDS must be > 0")
        if self.CHAT_VIDEO_CACHE_MAX_FILES <= 0:
            raise ValueError("CHAT_VIDEO_CACHE_MAX_FILES must be > 0")
        if not self.LOCAL_MEDIA_BASE_URL.startswith(("http://", "https://")):
            raise ValueError("LOCAL_MEDIA_BASE_URL must start with http:// or https://")
        if self.LOCAL_VIDEO_TRANSPORT_MODE not in {"data_url", "url"}:
            raise ValueError("LOCAL_VIDEO_TRANSPORT_MODE must be 'data_url' or 'url'")
        if self.MAX_VIDEO_DATA_URL_BYTES <= 0:
            raise ValueError("MAX_VIDEO_DATA_URL_BYTES must be > 0")
        if self.VISION_BACKEND not in {"glm", "local"}:
            raise ValueError("VISION_BACKEND must be 'glm' or 'local'")

        return self


# Global settings instance
settings = Settings()

# Directory paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / settings.CHROMA_PERSIST_DIR.split("/")[-1]

# Ensure directories exist
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
