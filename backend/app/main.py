"""AssistantBot FastAPI Application.

Main entry point for the backend API server.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings, MODELS_DIR, CHROMA_DIR
from app.api import chat, upload, health


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

        # Initialize LLM model
        from app.services.llm_service import get_llm
        print("  Loading LLM model (this may take a while)...")
        get_llm()
        print("  ✓ LLM model loaded")

        # Initialize vector database
        from app.services.rag_service import get_collection
        print("  Initializing vector database...")
        get_collection()
        print("  ✓ Vector database ready")

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
            "upload": f"{settings.API_V1_PREFIX}/documents/upload",
            "ingest_url": f"{settings.API_V1_PREFIX}/documents/ingest-url",
            "health": f"{settings.API_V1_PREFIX}/health/",
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
