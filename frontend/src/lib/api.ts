import type {
  HealthResponse,
  DocumentListResponse,
  DocumentDeleteResponse,
  DocumentUploadResponse,
  DocumentBatchUploadResponse,
  PerformanceOverviewResponse,
  ChatModeConfigResponse,
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
  has_file?: boolean;
  file_name?: string;
  file_format?: string;
  reasoning_content?: string;
  final_content?: string;
}

// Multimodal chat request with optional image
export interface MultimodalChatRequest {
  message: string;
  session_id?: string;
  use_search?: boolean;
  stream?: boolean;
  image?: string;  // Base64 encoded image
  image_format?: string;  // Image format (png, jpeg, webp, gif)
  file?: string;  // Base64 encoded file
  file_name?: string;
  file_format?: string;
  enable_thinking?: boolean;
  enable_tool_calling?: boolean;
  deploy_profile?: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const API = {
  chat: `${API_BASE_URL}/api/chat/`,
  stream: `${API_BASE_URL}/api/chat/stream`,
  chatModeConfig: `${API_BASE_URL}/api/chat/mode-config`,
  sessions: `${API_BASE_URL}/api/chat/sessions`,
  session: (id: string) => `${API_BASE_URL}/api/chat/sessions/${id}`,
  history: (id: string) => `${API_BASE_URL}/api/chat/history/${id}`,
  deleteSession: (id: string) => `${API_BASE_URL}/api/chat/history/${id}`,
  updateTitle: (id: string) => `${API_BASE_URL}/api/chat/sessions/${id}/title`,
  clearSessions: `${API_BASE_URL}/api/chat/sessions`,
  upload: `${API_BASE_URL}/api/documents/upload`,
  uploadBatch: `${API_BASE_URL}/api/documents/upload-batch`,
  ingestUrl: `${API_BASE_URL}/api/documents/ingest-url`,
  docs: `${API_BASE_URL}/api/documents/stats`,
  docsList: `${API_BASE_URL}/api/documents/list`,
  deleteDoc: (id: string) => `${API_BASE_URL}/api/documents/${id}`,
  clear: `${API_BASE_URL}/api/documents/clear`,
  health: `${API_BASE_URL}/api/health/`,
  performanceOverview: `${API_BASE_URL}/api/performance/overview`,
};

export async function healthCheck(): Promise<HealthResponse> {
  const response = await fetch(API.health);
  return response.json();
}

export async function getPerformanceOverview(): Promise<PerformanceOverviewResponse> {
  const response = await fetch(API.performanceOverview);
  if (!response.ok) {
    throw new Error(`Failed to fetch performance overview: ${response.statusText}`);
  }
  return response.json();
}

export async function getChatModeConfig(): Promise<ChatModeConfigResponse> {
  const response = await fetch(API.chatModeConfig);
  if (!response.ok) {
    throw new Error(`Failed to fetch chat mode config: ${response.statusText}`);
  }
  return response.json();
}

export async function updateChatModeConfig(deployProfile: string): Promise<ChatModeConfigResponse> {
  const response = await fetch(API.chatModeConfig, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deploy_profile: deployProfile }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update chat mode config: ${response.status} ${await response.text()}`);
  }
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
  fileData?: string,
  fileName?: string,
  fileFormat?: string,
  enableThinking?: boolean,
  enableToolCalling?: boolean,
  deployProfile?: string,
  onMetadata?: (metadata: {
    session_id?: string;
    sources?: Array<Record<string, unknown>>;
    has_context?: boolean;
    has_image?: boolean;
    has_file?: boolean;
    multimodal_mode?: string;
    deploy_profile?: string;
    requested_deploy_profile?: string;
    profile_source?: string;
    enable_thinking?: boolean;
    enable_tool_calling?: boolean;
    requested_enable_thinking?: boolean;
    requested_enable_tool_calling?: boolean;
    mode_warnings?: string[];
  }) => void,
  onDone?: (done: {
    session_id?: string;
    full_content?: string;
    display_content?: string;
    reasoning_content?: string | null;
    final_content?: string | null;
  }) => void,
): AsyncGenerator<string, void, unknown> {
  const hasImage = Boolean(imageData && imageData.trim());
  const hasFile = Boolean(fileData && fileData.trim());
  const trimmedMessage = message.trim();
  // Keep image-only requests valid for backend schema and model prompt.
  const effectiveMessage = trimmedMessage || (hasImage ? "请描述这张图片" : (hasFile ? "请阅读并总结这个文件的重点" : " "));

  const requestBody: MultimodalChatRequest = {
    message: effectiveMessage,
    session_id: sessionId,
    enable_thinking: Boolean(enableThinking),
    enable_tool_calling: Boolean(enableToolCalling),
    deploy_profile: deployProfile,
  };

  // Add image data if provided
  if (hasImage) {
    requestBody.image = imageData;
    requestBody.image_format = imageFormat || "png";
  }
  if (hasFile) {
    requestBody.file = fileData;
    requestBody.file_name = fileName;
    requestBody.file_format = fileFormat;
  }

  console.debug("Sending chat stream request", {
    session_id: sessionId,
    has_image: hasImage,
    has_file: hasFile,
    enable_thinking: Boolean(enableThinking),
    enable_tool_calling: Boolean(enableToolCalling),
    image_chars: imageData?.length ?? 0,
    file_chars: fileData?.length ?? 0,
    message_chars: effectiveMessage.length,
  });

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
            if (onMetadata) {
              onMetadata(parsed);
            }
          } else if (currentEvent === "token") {
            yield parsed.token || "";
          } else if (currentEvent === "done") {
            if (onDone) {
              onDone(parsed);
            }
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

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(API.upload, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`上传失败: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

export async function uploadDocuments(files: File[]): Promise<DocumentBatchUploadResponse> {
  if (!files.length) {
    throw new Error("No files provided");
  }

  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(API.uploadBatch, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`批量上传失败: ${response.status} ${await response.text()}`);
  }
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
