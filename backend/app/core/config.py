"""AssistantBot Core Configuration

Mac M3 optimized settings for Metal acceleration.
"""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Settings
    API_V1_PREFIX: str = "/api"
    PROJECT_NAME: str = "AssistantBot"
    VERSION: str = "0.1.0"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # LLM Settings (Qwen2.5-7B GGUF - much smarter model)
    MODEL_PATH: str = "./models/qwen2.5-7b-instruct-q3_k_m.gguf"
    N_GPU_LAYERS: int = -1  # -1 = offload all layers to Metal GPU
    N_CTX: int = 4096  # Context window size
    F16_KV: bool = True  # Use half-precision for KV cache
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2048
    TOP_P: float = 0.95
    TOP_K: int = 40

    # Chat template type (qwen, mistral, llama, etc.)
    CHAT_TEMPLATE_TYPE: str = "qwen"

    # Embedding Settings (GTE-large with MPS)
    EMBEDDING_MODEL: str = "thenlper/gte-large"
    EMBEDDING_DEVICE: str = "mps"  # Apple Silicon Neural Engine

    # Vision Model Settings
    # Choice: "glm" for GLM-4V API (recommended, no local model), "local" for BLIP-2
    VISION_BACKEND: str = "glm"  # "glm" or "local"

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

    class Config:
        env_file = ".env"
        case_sensitive = True


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
