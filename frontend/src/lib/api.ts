import type {
  HealthResponse,
  DocumentListResponse,
  DocumentDeleteResponse,
} from "../types";

// Session types
export interface Session {
  id: string;
  title: string;
  created: string;
  message_count: number;
  last_activity: string | null;
  last_message: string;
}

export interface SessionDetail {
  session_id: string;
  title: string;
  created: string;
  messages: ChatMessage[];
  message_count: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  // Multimodal support
  has_image?: boolean;
  image_data?: string;
  image_format?: string;
}

// Multimodal chat request with optional image
export interface MultimodalChatRequest {
  message: string;
  session_id?: string;
  use_search?: boolean;
  stream?: boolean;
  image?: string;  // Base64 encoded image
  image_format?: string;  // Image format (png, jpeg, webp, gif)
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const API = {
  chat: `${API_BASE_URL}/api/chat/`,
  stream: `${API_BASE_URL}/api/chat/stream`,
  sessions: `${API_BASE_URL}/api/chat/sessions`,
  session: (id: string) => `${API_BASE_URL}/api/chat/sessions/${id}`,
  history: (id: string) => `${API_BASE_URL}/api/chat/history/${id}`,
  deleteSession: (id: string) => `${API_BASE_URL}/api/chat/history/${id}`,
  updateTitle: (id: string) => `${API_BASE_URL}/api/chat/sessions/${id}/title`,
  clearSessions: `${API_BASE_URL}/api/chat/sessions`,
  upload: `${API_BASE_URL}/api/documents/upload`,
  ingestUrl: `${API_BASE_URL}/api/documents/ingest-url`,
  docs: `${API_BASE_URL}/api/documents/stats`,
  docsList: `${API_BASE_URL}/api/documents/list`,
  deleteDoc: (id: string) => `${API_BASE_URL}/api/documents/${id}`,
  clear: `${API_BASE_URL}/api/documents/clear`,
  health: `${API_BASE_URL}/api/health/`,
};

export async function healthCheck(): Promise<HealthResponse> {
  const response = await fetch(API.health);
  return response.json();
}

export async function sendMessage(message: string, sessionId?: string) {
  const response = await fetch(API.chat, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      stream: false,
    }),
  });
  return response.json();
}

export async function* streamMessage(
  message: string,
  sessionId?: string,
  imageData?: string,
  imageFormat?: string,
): AsyncGenerator<string, void, unknown> {
  // When image is provided but message is empty, use a space as placeholder
  const effectiveMessage = (message.trim() || (imageData && imageData.trim())) ? message.trim() : " ";

  const requestBody: MultimodalChatRequest = {
    message: effectiveMessage,
    session_id: sessionId,
  };

  // Add image data if provided
  if (imageData && imageData.trim()) {
    requestBody.image = imageData;
    requestBody.image_format = imageFormat || "png";
  }

  console.log("Sending request:", requestBody);

  const response = await fetch(API.stream, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error("API Error:", response.status, errorText);
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    throw new Error("No response body");
  }

  let buffer = "";
  let currentEvent = "";
  const sessionIdRef = { current: sessionId };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.trim() === "") continue;

      if (line.startsWith("event: ")) {
        // SSE event type line
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        // SSE data line
        const data = line.slice(6);
        try {
          const parsed = JSON.parse(data);
          if (currentEvent === "metadata") {
            sessionIdRef.current = parsed.session_id;
          } else if (currentEvent === "token") {
            yield parsed.token || "";
          } else if (currentEvent === "done") {
            return;
          } else if (currentEvent === "error") {
            throw new Error(parsed.error || "Unknown error");
          }
        } catch (e) {
          console.error("Failed to parse SSE data:", data, e);
        }
      }
    }
  }
}

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(API.upload, {
    method: "POST",
    body: formData,
  });
  return response.json();
}

export async function ingestUrls(urls: string[]) {
  const response = await fetch(API.ingestUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls }),
  });
  return response.json();
}

export async function getDocumentStats() {
  const response = await fetch(API.docs);
  return response.json();
}

export async function clearDocuments() {
  const response = await fetch(API.clear, {
    method: "DELETE",
  });
  return response.json();
}

export async function getDocumentList(): Promise<DocumentListResponse> {
  const response = await fetch(API.docsList);
  if (!response.ok) {
    throw new Error(`Failed to fetch document list: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteDocument(
  documentId: string
): Promise<DocumentDeleteResponse> {
  const response = await fetch(API.deleteDoc(documentId), {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete document: ${response.statusText}`);
  }
  return response.json();
}

// Session Management APIs
export async function getSessions(): Promise<{ sessions: Session[]; total: number }> {
  const response = await fetch(API.sessions);
  if (!response.ok) {
    throw new Error(`Failed to fetch sessions: ${response.statusText}`);
  }
  return response.json();
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(API.history(sessionId));
  if (!response.ok) {
    throw new Error(`Failed to fetch session: ${response.statusText}`);
  }
  return response.json();
}

export async function createSession(title?: string): Promise<{ session_id: string; title: string; message: string }> {
  const url = title ? `${API.sessions}?title=${encodeURIComponent(title)}` : API.sessions;
  const response = await fetch(url, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Failed to create session: ${response.statusText}`);
  }
  return response.json();
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<{ updated: boolean; session_id: string; title: string }> {
  const response = await fetch(API.updateTitle(sessionId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update session title: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteSession(sessionId: string): Promise<{ deleted: boolean; session_id: string }> {
  const response = await fetch(API.deleteSession(sessionId), {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.statusText}`);
  }
  return response.json();
}

export async function clearAllSessions(): Promise<{ deleted: boolean; count: number; message: string }> {
  const response = await fetch(API.clearSessions, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to clear sessions: ${response.statusText}`);
  }
  return response.json();
}

export type { HealthResponse };
