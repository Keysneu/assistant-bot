import type {
  HealthResponse,
  DocumentListResponse,
  DocumentDeleteResponse,
  DocumentUploadResponse,
  DocumentBatchUploadResponse,
  PerformanceOverviewResponse,
  ChatModeConfigResponse,
  ChatImageUploadResponse,
  ChatAudioUploadResponse,
  ChatVideoUploadResponse,
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
  image_id?: string;
  image_ids?: string[];
  image_url?: string;
  image_urls?: string[];
  has_file?: boolean;
  file_name?: string;
  file_format?: string;
  has_audio?: boolean;
  audio_url?: string;
  audio_urls?: string[];
  has_video?: boolean;
  video_url?: string;
  video_urls?: string[];
  reasoning_content?: string;
  final_content?: string;
  tool_traces?: Array<Record<string, unknown>>;
}

// Multimodal chat request with optional image
export interface MultimodalChatRequest {
  message: string;
  session_id?: string;
  use_search?: boolean;
  stream?: boolean;
  image_id?: string;
  image_ids?: string[];
  image?: string;  // Base64 encoded image
  images?: string[]; // Multiple base64 encoded images
  image_format?: string;  // Image format (png, jpeg, webp, gif)
  image_formats?: string[]; // Image formats aligned with `images`
  file?: string;  // Base64 encoded file
  file_name?: string;
  file_format?: string;
  audio_url?: string;
  audio_urls?: string[];
  video_url?: string;
  video_urls?: string[];
  enable_thinking?: boolean;
  enable_tool_calling?: boolean;
  response_format?: {
    type: "json_schema";
    json_schema: {
      name: string;
      schema: Record<string, unknown>;
      strict?: boolean;
    };
  };
}

function resolveDefaultApiBaseUrl(): string {
  const configured = String(import.meta.env.VITE_API_URL || "").trim();
  if (configured) {
    return configured.replace(/\/+$/, "");
  }

  if (typeof window !== "undefined" && window.location?.hostname) {
    const host = String(window.location.hostname || "").toLowerCase();
    // Prefer IPv4 loopback for local dev to avoid localhost IPv6 (::1) conflicts.
    if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]") {
      return "http://127.0.0.1:8000";
    }
    const protocol = window.location.protocol === "https:" ? "https:" : "http:";
    return `${protocol}//${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}

export const API_BASE_URL = resolveDefaultApiBaseUrl();

export const API = {
  chat: `${API_BASE_URL}/api/chat/`,
  stream: `${API_BASE_URL}/api/chat/stream`,
  chatImageUpload: `${API_BASE_URL}/api/chat/images/upload`,
  chatImage: (id: string) => `${API_BASE_URL}/api/chat/images/${id}`,
  chatAudioUpload: `${API_BASE_URL}/api/chat/audios/upload`,
  chatAudio: (id: string) => `${API_BASE_URL}/api/chat/audios/${id}`,
  chatVideoUpload: `${API_BASE_URL}/api/chat/videos/upload`,
  chatVideo: (id: string) => `${API_BASE_URL}/api/chat/videos/${id}`,
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

export function resolveApiUrl(rawUrl: string | undefined | null): string | undefined {
  const value = String(rawUrl || "").trim();
  if (!value) {
    return undefined;
  }
  try {
    return new URL(value, API_BASE_URL).toString();
  } catch {
    return undefined;
  }
}

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
  imageId?: string,
  imageFormat?: string,
  fileData?: string,
  fileName?: string,
  fileFormat?: string,
  enableThinking?: boolean,
  enableToolCalling?: boolean,
  onMetadata?: (metadata: {
    session_id?: string;
    sources?: Array<Record<string, unknown>>;
    has_context?: boolean;
    has_image?: boolean;
    has_audio?: boolean;
    has_video?: boolean;
    image_id?: string;
    image_ids?: string[];
    image_count?: number;
    audio_url?: string;
    audio_urls?: string[];
    audio_count?: number;
    audio_prefetched_count?: number;
    video_url?: string;
    video_urls?: string[];
    video_count?: number;
    has_file?: boolean;
    multimodal_mode?: string;
    deploy_profile?: string;
    requested_deploy_profile?: string;
    profile_source?: string;
    enable_thinking?: boolean;
    enable_tool_calling?: boolean;
    enable_structured_output?: boolean;
    requested_enable_thinking?: boolean;
    requested_enable_tool_calling?: boolean;
    requested_structured_output?: boolean;
    response_format_type?: string;
    response_schema_name?: string;
    mode_warnings?: string[];
    tool_traces?: Array<Record<string, unknown>>;
    tool_trace_count?: number;
  }) => void,
  onDone?: (done: {
    session_id?: string;
    full_content?: string;
    display_content?: string;
    reasoning_content?: string | null;
    final_content?: string | null;
    tool_traces?: Array<Record<string, unknown>>;
    tool_trace_count?: number;
  }) => void,
  onReasoningToken?: (token: string) => void,
  onToolTrace?: (trace: Record<string, unknown>) => void,
  imageIds?: string[],
  audioUrl?: string,
  audioUrls?: string[],
  videoUrl?: string,
  videoUrls?: string[],
  responseFormat?: MultimodalChatRequest["response_format"],
): AsyncGenerator<string, void, unknown> {
  const normalizedImageIds = (imageIds || []).map((item) => item.trim()).filter(Boolean);
  const normalizedAudioUrls = [audioUrl || "", ...(audioUrls || [])]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const normalizedVideoUrls = [videoUrl || "", ...(videoUrls || [])]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const hasImage = Boolean((imageId && imageId.trim()) || normalizedImageIds.length > 0);
  const hasAudio = normalizedAudioUrls.length > 0;
  const hasVideo = normalizedVideoUrls.length > 0;
  const hasFile = Boolean(fileData && fileData.trim());
  const trimmedMessage = message.trim();
  // Keep image-only requests valid for backend schema and model prompt.
  // Audio/Video/File are sent as native multimodal blocks alongside the text - no extra emphasis needed.
  const effectiveMessage = trimmedMessage || (
    hasImage
      ? "请描述这张图片"
      : (
        hasAudio
          ? " "  // Audio is sent as native multimodal block; Gemma4 handles it directly
          : (
            hasVideo
              ? "请总结视频里发生了什么，并提取关键事件和时间线。如果视频中有人提问，请直接回答。"
              : (hasFile ? "请阅读并总结这个文件的重点" : " ")
          )
      )
  );

  const requestBody: MultimodalChatRequest = {
    message: effectiveMessage,
    session_id: sessionId,
    enable_thinking: Boolean(enableThinking),
    enable_tool_calling: Boolean(enableToolCalling),
    ...(responseFormat ? { response_format: responseFormat } : {}),
  };

  // Add cached image reference if provided
  if (hasImage) {
    if (normalizedImageIds.length > 0) {
      requestBody.image_ids = normalizedImageIds;
    } else {
      requestBody.image_id = imageId;
      requestBody.image_format = imageFormat || "jpeg";
    }
  }
  if (hasFile) {
    requestBody.file = fileData;
    requestBody.file_name = fileName;
    requestBody.file_format = fileFormat;
  }
  if (hasAudio) {
    requestBody.audio_url = normalizedAudioUrls[0];
    if (normalizedAudioUrls.length > 1) {
      requestBody.audio_urls = normalizedAudioUrls;
    }
  }
  if (hasVideo) {
    requestBody.video_url = normalizedVideoUrls[0];
    if (normalizedVideoUrls.length > 1) {
      requestBody.video_urls = normalizedVideoUrls;
    }
  }

  console.debug("Sending chat stream request", {
    session_id: sessionId,
    has_image: hasImage,
    has_audio: hasAudio,
    has_video: hasVideo,
    has_file: hasFile,
    enable_thinking: Boolean(enableThinking),
    enable_tool_calling: Boolean(enableToolCalling),
    image_id: imageId || "",
    image_ids: normalizedImageIds,
    audio_urls: normalizedAudioUrls,
    video_urls: normalizedVideoUrls,
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
          } else if (currentEvent === "reasoning") {
            const token = String(parsed.token || "");
            if (token && onReasoningToken) {
              onReasoningToken(token);
            }
          } else if (currentEvent === "tool_trace") {
            if (onToolTrace && parsed?.trace && typeof parsed.trace === "object") {
              onToolTrace(parsed.trace as Record<string, unknown>);
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

export async function uploadChatImage(file: File): Promise<ChatImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(API.chatImageUpload, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`图片上传失败: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

export async function uploadChatAudio(file: File): Promise<ChatAudioUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(API.chatAudioUpload, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`音频上传失败: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

export async function uploadChatVideo(file: File): Promise<ChatVideoUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(API.chatVideoUpload, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`视频上传失败: ${response.status} ${await response.text()}`);
  }
  return response.json();
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
