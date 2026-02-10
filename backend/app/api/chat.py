"""Chat API endpoints.

Handles streaming and non-streaming chat responses with RAG support.
"""
import json
import uuid
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

    Args:
        request: Chat request with message and session info

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

    # Add user message to history
    add_message(session_id, "user", request.message)

    # Retrieve relevant documents
    sources = []
    context = ""
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

    async def event_generator():
        """Generate SSE events for streaming response."""
        try:
            # Send initial metadata
            yield {
                "event": "metadata",
                "data": json.dumps({
                    "session_id": session_id,
                    "sources": sources,
                    "has_context": bool(context),
                }),
            }

            # Stream response (hybrid mode: use RAG when available, free chat otherwise)
            full_response = ""
            async for token in astream_response(request.message, context):
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
