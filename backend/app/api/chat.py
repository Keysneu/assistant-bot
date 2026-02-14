"""Chat API endpoints.

Handles streaming and non-streaming chat responses with RAG support.
Multimodal support for image understanding using BLIP-2 vision model.
"""
import base64
import json
import re
import uuid
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.models.schema import ChatRequest, ChatResponse, ErrorResponse, SessionTitleRequest
from app.services.llm_service import generate_response, astream_response, is_model_loaded, get_llm
from app.services.rag_service import retrieve, get_context
from app.services.session_service import (
    create_session,
    add_message,
    get_history,
    get_context_for_query,
    get_all_sessions,
    get_session_info,
    update_session_title,
    clear_all_sessions,
)
from app.services.rag_service import verify_content_relevance
from app.services.vision_service import (
    analyze_image_content,
    is_vision_available,
    get_supported_formats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat request (non-streaming).

    Args:
        request: Chat request with message and session info

    Returns:
        Chat response with generated content and sources
    """
    # Trigger lazy loading if model not loaded
    if not is_model_loaded():
        try:
            get_llm()  # This will load the model
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Model loading failed: {str(e)}")

    # Create or use existing session
    session_id = request.session_id or create_session()

    # Add user message to history
    add_message(session_id, "user", request.message)

    # Retrieve relevant documents if not using web search
    sources = []
    context = ""
    has_relevant_context = False

    if not request.use_search:
        try:
            # Use conversation context for query
            query_with_context = get_context_for_query(session_id, request.message)
            documents = retrieve(query_with_context)
            if documents:
                # Check if we have high-relevance documents
                avg_score = sum(d.score or 0 for d in documents) / len(documents)
                score_check = avg_score > 0.4  # Threshold for "relevant enough"

                # Secondary check: verify content actually contains relevant terms
                content_check = verify_content_relevance(request.message, documents)

                has_relevant_context = score_check and content_check

                if has_relevant_context:
                    context = get_context(documents)
                    sources = [
                        {
                            "content": doc.content[:200] + "...",
                            "source": doc.metadata.get("source", "Unknown"),
                            "score": doc.score,
                        }
                        for doc in documents
                    ]
        except Exception as e:
            # RAG failed, continue without context
            import logging
            logging.warning(f"RAG retrieval failed: {e}, continuing without context")

    # Generate response (hybrid mode: use RAG when available, free chat otherwise)
    try:
        # Generate response - if context exists, use it; otherwise free chat
        response_text = generate_response(request.message, context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

    # Add assistant message to history
    add_message(session_id, "assistant", response_text)

    return ChatResponse(
        content=response_text,
        session_id=session_id,
        sources=sources,
        metadata={"model": "qwen2.5-7b", "use_rag": bool(context)},
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """Process a chat request with streaming response.

    Supports multimodal input when an image is provided in the request.

    Args:
        request: Chat request with message, optional image, and session info

    Returns:
        Streaming SSE response with generated tokens
    """
    # Trigger lazy loading if model not loaded
    if not is_model_loaded():
        try:
            get_llm()  # This will load the model
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Model loading failed: {str(e)}")

    # Create or use existing session
    session_id = request.session_id or create_session()

    # ==================== MULTIMODAL IMAGE PROCESSING ====================
    image_context = ""
    has_image = False

    if request.image:
        try:
            logger.info(f"Image data received, length: {len(request.image)}")
            # Decode base64 image
            image_bytes = base64.b64decode(request.image)

            # Check if vision service is available (GLM-4V API or local model)
            if is_vision_available():
                # Generate image description using GLM-4V API
                logger.info("Processing image with GLM-4V API...")
                try:
                    image_context = await analyze_image_content(
                        image_bytes,
                        user_question=request.message,
                    )
                    has_image = True
                    logger.info(f"Image context generated: {len(image_context)} chars")
                except RuntimeError as vision_error:
                    # Vision API unavailable - graceful degradation
                    logger.warning(f"Vision service unavailable: {vision_error}, continuing without image analysis")
                    image_context = ""
                except Exception as e:
                    logger.error(f"Vision processing failed: {e}", exc_info=True)
                    # Continue without image context rather than failing
                    image_context = ""
            else:
                logger.warning("Vision service not available, skipping image analysis")
                image_context = ""

        except Exception as e:
            logger.error(f"Image decode/processing failed: {e}", exc_info=True)
            # Continue without image context rather than failing
            image_context = ""
    # ====================================================================

    # Prepare image data for history storage
    image_data_to_store = None
    image_format_to_store = None

    if request.image:
        try:
            logger.info(f"Image data received, length: {len(request.image)}")
            # Decode base64 image
            image_bytes = base64.b64decode(request.image)

            # Extract format from data URL (e.g., "data:image/png;base64,...")
            import re
            if "image/" in request.image:
                match = re.search(r"data:image/([a-zA-Z+]+);base64,", request.image)
                image_format_to_store = match.group(1) if match else "png"

            # Store image data for message history
            image_data_to_store = request.image
        except Exception as e:
            logger.error(f"Image decode failed: {e}", exc_info=True)

    # ====================================================================

    # Add user message to history (with image data)
    add_message(
        session_id,
        "user",
        request.message,
        has_image=bool(image_data_to_store),
        image_data=image_data_to_store,
        image_format=image_format_to_store
    )

    # Retrieve relevant documents
    sources = []
    rag_context = ""
    has_relevant_context = False

    if not request.use_search:
        try:
            query_with_context = get_context_for_query(session_id, request.message)
            documents = retrieve(query_with_context)
            if documents:
                # Check if we have high-relevance documents
                avg_score = sum(d.score or 0 for d in documents) / len(documents)
                score_check = avg_score > 0.4

                # Secondary check: verify content actually contains relevant terms
                content_check = verify_content_relevance(request.message, documents)

                has_relevant_context = score_check and content_check

                if has_relevant_context:
                    rag_context = get_context(documents)
                    sources = [
                        {
                            "content": doc.content[:200] + "...",
                            "source": doc.metadata.get("source", "Unknown"),
                            "score": doc.score,
                        }
                        for doc in documents
                    ]
        except Exception as e:
            # RAG failed, continue without context
            logger.warning(f"RAG retrieval failed: {e}, continuing without context")

    # Combine contexts: image context + RAG context
    combined_context = ""
    if image_context:
        combined_context += image_context + "\n\n"
    if rag_context:
        combined_context += rag_context

    async def event_generator():
        """Generate SSE events for streaming response."""
        try:
            # Send initial metadata
            yield {
                "event": "metadata",
                "data": json.dumps({
                    "session_id": session_id,
                    "sources": sources,
                    "has_context": bool(combined_context),
                    "has_image": has_image,
                }),
            }

            # Stream response (hybrid mode: use combined context when available)
            full_response = ""
            effective_question = request.message
            async for token in astream_response(effective_question, combined_context):
                full_response += token
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token}),
                }

            # Send completion event
            yield {
                "event": "done",
                "data": json.dumps({
                    "session_id": session_id,
                    "full_content": full_response,
                }),
            }

            # Add to history after completion
            add_message(session_id, "assistant", full_response)

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/history/{session_id}")
async def get_session_history(session_id: str):
    """Get conversation history for a session.

    Args:
        session_id: Session identifier

    Returns:
        Session history with all messages
    """
    session = get_session_info(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "title": session.get("title", "未命名对话"),
        "created": session.get("created", ""),
        "messages": session.get("messages", []),
        "message_count": len(session.get("messages", []))
    }


@router.delete("/history/{session_id}")
async def delete_session_history(session_id: str):
    """Delete a conversation session.

    Args:
        session_id: Session identifier

    Returns:
        Deletion confirmation
    """
    from app.services.session_service import delete_session

    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"deleted": True, "session_id": session_id}


@router.get("/sessions")
async def list_sessions():
    """Get all conversation sessions.

    Returns:
        List of all sessions with metadata
    """
    sessions = get_all_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session with full message history.

    Args:
        session_id: Session identifier

    Returns:
        Session with full message history
    """
    session = get_session_info(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.post("/sessions")
async def create_new_session(title: str = None):
    """Create a new conversation session.

    Args:
        title: Optional title for the session

    Returns:
        New session info
    """
    from fastapi import Query

    # Parse title from query or body
    session_id = create_session(title)
    return {
        "session_id": session_id,
        "title": title or "新对话",
        "message": "新会话已创建"
    }


@router.put("/sessions/{session_id}/title")
async def rename_session(session_id: str, request: SessionTitleRequest):
    """Update the title of a session.

    Args:
        session_id: Session identifier
        request: Request body with title

    Returns:
        Updated session info
    """
    updated = update_session_title(session_id, request.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"updated": True, "session_id": session_id, "title": request.title}


@router.delete("/sessions")
async def clear_all_session_history():
    """Clear all conversation sessions.

    Returns:
        Deletion confirmation with count
    """
    count = clear_all_sessions()
    return {"deleted": True, "count": count, "message": f"已清除 {count} 个会话"}
