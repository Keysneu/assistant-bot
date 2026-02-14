"""Session Service for managing conversation history with persistence.

Stores conversation history in JSON file with support for multiple sessions.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.models.schema import ChatMessage
from app.core.config import DATA_DIR

# Session storage file
SESSIONS_FILE = DATA_DIR / "sessions.json"


# In-memory session storage (loaded from file on startup)
_sessions: Dict[str, List[ChatMessage]] = {}
_session_titles: Dict[str, str] = {}  # session_id -> title
_session_created: Dict[str, str] = {}  # session_id -> ISO timestamp


def _load_sessions():
    """Load sessions from file on startup."""
    global _sessions, _session_titles, _session_created

    if SESSIONS_FILE.exists():
        try:
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for session_id, messages_data in data.get("sessions", {}).items():
                _sessions[session_id] = [
                    ChatMessage(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=datetime.fromisoformat(msg["timestamp"]) if msg.get("timestamp") else None
                    )
                    for msg in messages_data
                ]

            _session_titles = data.get("titles", {})
            _session_created = data.get("created", {})

        except Exception as e:
            import logging
            logging.warning(f"Failed to load sessions: {e}")


def _save_sessions():
    """Save sessions to file."""
    data = {
        "sessions": {},
        "titles": _session_titles,
        "created": _session_created,
    }

    for session_id, messages in _sessions.items():
        data["sessions"][session_id] = [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "has_image": msg.has_image if hasattr(msg, "has_image") else False,
                "image_data": msg.image_data if hasattr(msg, "image_data") else None,
                "image_format": msg.image_format if hasattr(msg, "image_format") else None,
            }
            for msg in messages
        ]

    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Initialize on import
_load_sessions()


def create_session(title: str = None) -> str:
    """Create a new conversation session.

    Args:
        title: Optional title for the session

    Returns:
        Session ID
    """
    session_id = str(uuid.uuid4())
    _sessions[session_id] = []
    _session_created[session_id] = datetime.utcnow().isoformat()

    # Set title or use default
    if title:
        _session_titles[session_id] = title
    else:
        _session_titles[session_id] = f"新对话 {len(_sessions)}"

    _save_sessions()
    return session_id


def add_message(
    session_id: str,
    role: str,
    content: str,
    has_image: bool = False,
    image_data: str = None,
    image_format: str = None
) -> ChatMessage:
    """Add a message to the conversation history.

    Args:
        session_id: Session identifier
        role: Message role ('user' or 'assistant')
        content: Message content
        has_image: Whether the message has an attached image
        image_data: Base64 encoded image data
        image_format: Image format (png, jpeg, etc.)

    Returns:
        The created message
    """
    if session_id not in _sessions:
        _sessions[session_id] = []
        _session_created[session_id] = datetime.utcnow().isoformat()

    message = ChatMessage(
        role=role,
        content=content,
        timestamp=datetime.utcnow(),
        has_image=has_image,
        image_data=image_data,
        image_format=image_format,
    )
    _sessions[session_id].append(message)

    # Auto-generate title from first user message if not set
    if session_id not in _session_titles or _session_titles[session_id].startswith("新对话"):
        if role == "user" and len(_sessions[session_id]) <= 2:
            # Use first 30 chars of first message as title
            title = content[:30] + "..." if len(content) > 30 else content
            _session_titles[session_id] = title

    _save_sessions()
    return message


def get_history(session_id: str) -> List[ChatMessage]:
    """Get conversation history for a session.

    Args:
        session_id: Session identifier

    Returns:
        List of messages in the session
    """
    return _sessions.get(session_id, [])


def get_session_ids() -> List[str]:
    """Get all active session IDs.

    Returns:
        List of session IDs
    """
    return list(_sessions.keys())


def get_all_sessions() -> List[Dict]:
    """Get all sessions with metadata.

    Returns:
        List of session dictionaries with id, title, created, message_count, last_message
    """
    sessions = []
    for session_id in _sessions.keys():
        messages = _sessions[session_id]
        last_msg = messages[-1] if messages else None

        # Get last message preview (first message or last user message)
        last_message_preview = ""
        if messages:
            # Try to find last user message for preview
            for msg in reversed(messages):
                if msg.role == "user":
                    last_message_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
                    break
            # If no user message, use first message
            if not last_message_preview:
                last_message_preview = messages[0].content[:50] + "..." if len(messages[0].content) > 50 else messages[0].content

        sessions.append({
            "id": session_id,
            "title": _session_titles.get(session_id, "未命名对话"),
            "created": _session_created.get(session_id, ""),
            "message_count": len(messages),
            "last_activity": last_msg.timestamp.isoformat() if last_msg else None,
            "last_message": last_message_preview
        })

    # Sort by created time (newest first)
    sessions.sort(key=lambda x: x["created"], reverse=True)
    return sessions


def get_session_info(session_id: str) -> Optional[Dict]:
    """Get detailed information about a session.

    Args:
        session_id: Session identifier

    Returns:
        Session info dict or None if not found
    """
    if session_id not in _sessions:
        return None

    return {
        "id": session_id,
        "title": _session_titles.get(session_id, "未命名对话"),
        "created": _session_created.get(session_id, ""),
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "has_image": msg.has_image if hasattr(msg, "has_image") else False,
                "image_data": msg.image_data if hasattr(msg, "image_data") else None,
                "image_format": msg.image_format if hasattr(msg, "image_format") else None,
            }
            for msg in _sessions[session_id]
        ]
    }


def update_session_title(session_id: str, title: str) -> bool:
    """Update the title of a session.

    Args:
        session_id: Session identifier
        title: New title

    Returns:
        True if updated, False if session not found
    """
    if session_id not in _sessions:
        return False

    _session_titles[session_id] = title
    _save_sessions()
    return True


def delete_session(session_id: str) -> bool:
    """Delete a session.

    Args:
        session_id: Session identifier

    Returns:
        True if session was deleted, False if not found
    """
    if session_id in _sessions:
        del _sessions[session_id]
        if session_id in _session_titles:
            del _session_titles[session_id]
        if session_id in _session_created:
            del _session_created[session_id]
        _save_sessions()
        return True
    return False


def clear_all_sessions() -> int:
    """Clear all sessions.

    Returns:
        Number of sessions deleted
    """
    count = len(_sessions)
    _sessions.clear()
    _session_titles.clear()
    _session_created.clear()
    _save_sessions()
    return count


def format_conversation(messages: List[ChatMessage]) -> str:
    """Format messages into a conversation string for the LLM.

    Args:
        messages: List of chat messages

    Returns:
        Formatted conversation string
    """
    if not messages:
        return ""

    parts = []
    for msg in messages:
        if msg.role == "user":
            parts.append(f"User: {msg.content}")
        else:
            parts.append(f"Assistant: {msg.content}")

    return "\n".join(parts)


def get_context_for_query(session_id: str, current_query: str) -> str:
    """Get conversation context for a follow-up query.

    Args:
        session_id: Session identifier
        current_query: Current user query

    Returns:
        Context string with recent conversation
    """
    messages = get_history(session_id)

    # Get last 6 messages (3 turns) for context
    recent_messages = messages[-6:] if len(messages) > 6 else messages

    if not recent_messages:
        return current_query

    conversation = format_conversation(recent_messages)
    return f"{conversation}\nUser: {current_query}"
