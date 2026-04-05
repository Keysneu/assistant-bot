"""AssistantBot FastAPI Application.

Main entry point for the backend API server.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings, MODELS_DIR, CHROMA_DIR
from app.api import chat, upload, health, performance


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    print(f"🚀 Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"📁 Models directory: {MODELS_DIR}")
    print(f"📦 ChromaDB directory: {CHROMA_DIR}")

    # Initialize services on startup
    print("⏳ Initializing services...")
    try:
        # Initialize embedding model
        from app.services.embedding_service import get_embedding_model
        print("  Loading embedding model...")
        get_embedding_model()
        print("  ✓ Embedding model loaded")

        # Initialize LLM backend
        if settings.LLM_PROVIDER == "vllm":
            from app.services.llm_service import probe_vllm_connection
            print(f"  Checking vLLM endpoint: {settings.VLLM_BASE_URL} ...")
            vllm_ready, reason = probe_vllm_connection()
            if not vllm_ready:
                raise RuntimeError(reason or "vLLM check failed")
            print(f"  ✓ vLLM endpoint reachable, model={settings.VLLM_MODEL}")
        else:
            from app.services.llm_service import get_llm
            print("  Loading LLM model (this may take a while)...")
            get_llm()
            print("  ✓ LLM model loaded")

        # Initialize vector database
        from app.services.rag_service import get_collection
        print("  Initializing vector database...")
        get_collection()
        print("  ✓ Vector database ready")

        # Initialize vision model for multimodal support (legacy proxy path)
        if settings.LLM_PROVIDER == "vllm":
            print("  vLLM provider active: Gemma4 native multimodal will be used for image chat")
            if settings.DISABLE_GLM_VISION:
                print("  ✓ GLM vision proxy disabled by config")
            else:
                print("  ℹ️ GLM vision proxy is enabled but not used for vLLM image requests")
        else:
            from app.services.vision_service import is_vision_available
            print("  Checking vision service availability...")
            if is_vision_available():
                print("  ✓ Vision service ready")
            else:
                print("  ⚠️ Vision service unavailable (image analysis disabled)")

        print("✅ All services initialized successfully!")
    except Exception as e:
        print(f"⚠️ Service initialization error: {e}")
        print("⚠️ Services will be initialized on first request")

    yield

    # Shutdown
    print("👋 Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(upload.router, prefix=settings.API_V1_PREFIX)
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(performance.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
        "endpoints": {
            "chat": f"{settings.API_V1_PREFIX}/chat/",
            "stream": f"{settings.API_V1_PREFIX}/chat/stream",
            "chat_mode_config": f"{settings.API_V1_PREFIX}/chat/mode-config",
            "upload": f"{settings.API_V1_PREFIX}/documents/upload",
            "upload_batch": f"{settings.API_V1_PREFIX}/documents/upload-batch",
            "ingest_url": f"{settings.API_V1_PREFIX}/documents/ingest-url",
            "health": f"{settings.API_V1_PREFIX}/health/",
            "performance": f"{settings.API_V1_PREFIX}/performance/overview",
        },
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
