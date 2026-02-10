"""Embedding Service using sentence-transformers with MPS support.

Optimized for Mac M3 Neural Engine acceleration.
"""
from typing import List

from sentence_transformers import SentenceTransformer
from app.core.config import settings

# Global embedding model instance
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the embedding model (singleton pattern)."""
    global _embedding_model
    if _embedding_model is None:
        # Load model with MPS device for Mac M3 Neural Engine
        _embedding_model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device=settings.EMBEDDING_DEVICE,
        )
    return _embedding_model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors
    """
    model = get_embedding_model()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def embed_query(query: str) -> List[float]:
    """Generate embedding for a single query.

    Args:
        query: Query string to embed

    Returns:
        Embedding vector
    """
    return embed_texts([query])[0]


def is_model_loaded() -> bool:
    """Check if the embedding model is loaded."""
    return _embedding_model is not None


def unload_model():
    """Unload the embedding model to free memory."""
    global _embedding_model
    _embedding_model = None
