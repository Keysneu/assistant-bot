import { memo, useState, useRef, useEffect } from "react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Loader2, User, AlertCircle, Paperclip, X, Brain, Wrench, Info, Mic, Square, Video } from "lucide-react";
import type { ChatMessage, ChatModeConfigResponse } from "../types";
import { API, streamMessage, getSession, getChatModeConfig, uploadChatImage, uploadChatAudio, uploadChatVideo, resolveApiUrl } from "../lib/api";
import { parseThinkingContent } from "../utils/thinkingParser";
import { cn } from "../lib/utils";
import { Button } from "./ui/Button";
import { Skeleton } from "./ui/Skeleton";
import { ImageUploader, type SelectedImagePayload } from "./ImageUploader";
import { Logo } from "./Logo";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/Dialog";

interface ChatBoxProps {
  sessionId?: string;
  onSessionChange?: (sessionId: string) => void;
  onRefreshSessions?: () => void;
}

function isNetworkError(err: unknown): boolean {
  if (err instanceof TypeError) {
    return (
      err.message.includes("Failed to fetch") ||
      err.message.includes("NetworkError")
    );
  }
  return false;
}

type DeployProfileKey = "rag_text" | "vision" | "full" | "full_featured" | "benchmark" | "extreme";
type StreamDonePayload = {
  session_id?: string;
  full_content?: string;
  display_content?: string;
  reasoning_content?: string | null;
  final_content?: string | null;
};

const STREAM_FLUSH_INTERVAL_MS = 50;
const PROFILE_GUIDE: Record<
  DeployProfileKey,
  {
    title: string;
    description: string;
    supportsImage: boolean;
    supportsAudio: boolean;
    supportsVideo: boolean;
    supportsThinking: boolean;
    supportsToolCalling: boolean;
  }
> = {
  rag_text: {
    title: "文本 RAG 档位",
    description: "优先文本问答与检索，禁用图片/音频/视频与工具调用。",
    supportsImage: false,
    supportsAudio: false,
    supportsVideo: false,
    supportsThinking: true,
    supportsToolCalling: false,
  },
  vision: {
    title: "图文档位",
    description: "开启图片理解，适合图文问答，不开启音频/视频与工具调用。",
    supportsImage: true,
    supportsAudio: false,
    supportsVideo: false,
    supportsThinking: true,
    supportsToolCalling: false,
  },
  full: {
    title: "全能力档位",
    description: "支持图片、音频、视频、Thinking 与 Tool Calling。",
    supportsImage: true,
    supportsAudio: true,
    supportsVideo: true,
    supportsThinking: true,
    supportsToolCalling: true,
  },
  full_featured: {
    title: "全功能官方档位",
    description: "对齐 Gemma4 full-featured 参数，开启图片、音频、视频、Thinking 与 Tool Calling。",
    supportsImage: true,
    supportsAudio: true,
    supportsVideo: true,
    supportsThinking: true,
    supportsToolCalling: true,
  },
  benchmark: {
    title: "压测档位",
    description: "用于稳定压测，关闭图片、Thinking 与 Tool Calling。",
    supportsImage: false,
    supportsAudio: false,
    supportsVideo: false,
    supportsThinking: false,
    supportsToolCalling: false,
  },
  extreme: {
    title: "极限资源档位",
    description: "最大化资源占用，关闭图片、Thinking 与 Tool Calling。",
    supportsImage: false,
    supportsAudio: false,
    supportsVideo: false,
    supportsThinking: false,
    supportsToolCalling: false,
  },
};

const AssistantContent = memo(function AssistantContent({
  content,
  isStreaming,
  reasoningContent,
  finalContent,
  preferThinkingPanel,
}: {
  content: string;
  isStreaming: boolean;
  reasoningContent?: string;
  finalContent?: string;
  preferThinkingPanel?: boolean;
}) {
  const renderMarkdown = (markdown: string) => (
    <div className="markdown-content prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }: ComponentPropsWithoutRef<"code"> & { children?: ReactNode }) {
            const isInline = !children?.toString().includes("\n");
            return (
              <code
                className={cn(
                  isInline
                    ? "bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground"
                    : "block bg-muted/50 p-4 rounded-lg text-sm overflow-x-auto font-mono my-2 border border-border",
                  className
                )}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre({ children }: ComponentPropsWithoutRef<"pre">) {
            return <>{children}</>;
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );

  if (reasoningContent || finalContent) {
    const normalizedFinal = (finalContent || content || "").trim();
    const normalizedReasoning = (reasoningContent || "").trim();

    if (!normalizedReasoning) {
      const fallbackCandidate = normalizedFinal || content || "";
      if (/^thought\s*/i.test(fallbackCandidate.trim())) {
        const parsed = parseThinkingContent(fallbackCandidate);
        const parsedReasoning = parsed?.reasoning?.trim() || "";
        const parsedAnswer = parsed?.answer?.trim() || "";
        if (parsedReasoning) {
          return (
            <div className="space-y-3">
              <details className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
                <summary className="cursor-pointer list-none text-xs text-muted-foreground flex items-center gap-1.5">
                  <Brain className="w-3.5 h-3.5" />
                  <span>思考过程</span>
                </summary>
                <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
                  {renderMarkdown(parsedReasoning)}
                </div>
              </details>
              {renderMarkdown(parsedAnswer || normalizedFinal)}
            </div>
          );
        }
      }
      if (isStreaming && !normalizedFinal) {
        return <span className="animate-pulse">...</span>;
      }
      return renderMarkdown(normalizedFinal);
    }

    return (
      <div className="space-y-3">
        <details className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer list-none text-xs text-muted-foreground flex items-center gap-1.5">
            <Brain className="w-3.5 h-3.5" />
            <span>思考过程</span>
          </summary>
          <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
            {renderMarkdown(normalizedReasoning)}
          </div>
        </details>
        {renderMarkdown(normalizedFinal || normalizedReasoning)}
      </div>
    );
  }

  if (isStreaming && preferThinkingPanel) {
    const parsed = parseThinkingContent(content);
    if (!parsed) {
      return (
        <div className="space-y-3">
          <div className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Brain className="w-3.5 h-3.5" />
              <span>思考中...</span>
            </div>
            <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
              {content.trim() ? renderMarkdown(content) : <span className="animate-pulse">正在思考...</span>}
            </div>
          </div>
          <span className="text-xs text-muted-foreground animate-pulse">正在整理最终回答...</span>
        </div>
      );
    }

    if (parsed) {
      const reasoning = parsed.reasoning.trim();
      const answer = parsed.answer.trim();
      const hasReasoning = Boolean(reasoning);
      const hasAnswer = Boolean(answer);

      return (
        <div className="space-y-3">
          <div className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Brain className="w-3.5 h-3.5" />
              <span>{hasAnswer ? "思考完成" : "思考中..."}</span>
            </div>
            <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
              {hasReasoning ? renderMarkdown(reasoning) : <span className="animate-pulse">正在思考...</span>}
            </div>
          </div>
          {hasAnswer ? (
            renderMarkdown(answer)
          ) : (
            <span className="text-xs text-muted-foreground animate-pulse">正在整理最终回答...</span>
          )}
        </div>
      );
    }
  }

  if (isStreaming && !content.trim()) {
    return <span className="animate-pulse">...</span>;
  }
  return renderMarkdown(content);
});

export function ChatBox({
  sessionId,
  onSessionChange,
  onRefreshSessions,
}: ChatBoxProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isBackendAvailable, setIsBackendAvailable] = useState(true);
  // Multimodal state
  const [selectedImages, setSelectedImages] = useState<SelectedImagePayload[]>([]);
  const [selectedFileData, setSelectedFileData] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [selectedFileFormat, setSelectedFileFormat] = useState("");
  const [selectedVideoFile, setSelectedVideoFile] = useState<File | null>(null);
  const [selectedVideoName, setSelectedVideoName] = useState("");
  const [selectedVideoPreviewUrl, setSelectedVideoPreviewUrl] = useState("");
  const [selectedAudioFile, setSelectedAudioFile] = useState<File | null>(null);
  const [selectedAudioName, setSelectedAudioName] = useState("");
  const [selectedAudioPreviewUrl, setSelectedAudioPreviewUrl] = useState("");
  const [isRecordingAudio, setIsRecordingAudio] = useState(false);
  const [recordingElapsedSeconds, setRecordingElapsedSeconds] = useState(0);
  const [shouldAutoSubmitRecordedAudio, setShouldAutoSubmitRecordedAudio] = useState(false);
  const [enableThinkingMode, setEnableThinkingMode] = useState(false);
  const [enableToolCallingMode, setEnableToolCallingMode] = useState(false);
  const [modeConfig, setModeConfig] = useState<ChatModeConfigResponse | null>(null);
  const [modeWarnings, setModeWarnings] = useState<string[]>([]);
  const [streamingAssistantIndex, setStreamingAssistantIndex] = useState<number | null>(null);
  const [streamingAssistantContent, setStreamingAssistantContent] = useState("");
  const [streamingThinkingPanelLocked, setStreamingThinkingPanelLocked] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const hasAttemptedConnection = useRef(false);
  const messagesRef = useRef<ChatMessage[]>([]);
  const streamBufferRef = useRef("");
  const lastStreamFlushAtRef = useRef(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const loadModeConfig = async () => {
      try {
        const config = await getChatModeConfig();
        setModeConfig(config);
      } catch (error) {
        console.warn("加载模式配置失败，使用默认能力", error);
      }
    };
    loadModeConfig();
  }, []);

  useEffect(() => {
    const loadSessionHistory = async () => {
      if (sessionId) {
        setIsLoadingHistory(true);
        try {
          const session = await getSession(sessionId);
          const historyMessages = session.messages.map((msg) => ({
            role: msg.role as "user" | "assistant",
            content: msg.content,
            timestamp: new Date(msg.timestamp),
            // 多模态支持：保留图片相关字段
            has_image: msg.has_image,
            image_data: msg.image_data,
            image_format: msg.image_format,
            image_id: msg.image_id,
            image_ids: msg.image_ids,
            image_urls: msg.image_urls,
            has_file: msg.has_file,
            file_name: msg.file_name,
            file_format: msg.file_format,
            has_audio: msg.has_audio,
            audio_url: msg.audio_url,
            audio_urls: msg.audio_urls,
            has_video: msg.has_video,
            video_url: msg.video_url,
            video_urls: msg.video_urls,
            reasoning_content: msg.reasoning_content,
            final_content: msg.final_content,
          }));
          setMessages(historyMessages);
          setIsBackendAvailable(true);
        } catch (error) {
          if (isNetworkError(error)) {
            setIsBackendAvailable(false);
            if (!hasAttemptedConnection.current) {
              console.warn("后端服务器未运行");
              hasAttemptedConnection.current = true;
            }
          } else {
            console.error("加载会话历史失败:", error);
          }
          setMessages([]);
        } finally {
          setIsLoadingHistory(false);
        }
      } else {
        setMessages([]);
      }
    };

    loadSessionHistory();
  }, [sessionId]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (streamingAssistantIndex !== null && streamingAssistantContent) {
      scrollToBottom();
    }
  }, [streamingAssistantContent, streamingAssistantIndex]);

  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) {
        window.clearInterval(recordingTimerRef.current);
        recordingTimerRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      if (mediaStreamRef.current) {
        for (const track of mediaStreamRef.current.getTracks()) {
          track.stop();
        }
        mediaStreamRef.current = null;
      }
      if (selectedAudioPreviewUrl && selectedAudioPreviewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(selectedAudioPreviewUrl);
      }
      if (selectedVideoPreviewUrl && selectedVideoPreviewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(selectedVideoPreviewUrl);
      }
    };
  }, [selectedAudioPreviewUrl, selectedVideoPreviewUrl]);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  const stopMediaStreamTracks = () => {
    if (mediaStreamRef.current) {
      for (const track of mediaStreamRef.current.getTracks()) {
        track.stop();
      }
      mediaStreamRef.current = null;
    }
  };

  const clearRecordingTimer = () => {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
  };

  const formatRecordingDuration = (totalSeconds: number) => {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  };

  const resetSelectedAudio = () => {
    if (selectedAudioPreviewUrl && selectedAudioPreviewUrl.startsWith("blob:")) {
      URL.revokeObjectURL(selectedAudioPreviewUrl);
    }
    setSelectedAudioFile(null);
    setSelectedAudioName("");
    setSelectedAudioPreviewUrl("");
    if (audioInputRef.current) {
      audioInputRef.current.value = "";
    }
  };

  const resetSelectedVideo = () => {
    if (selectedVideoPreviewUrl && selectedVideoPreviewUrl.startsWith("blob:")) {
      URL.revokeObjectURL(selectedVideoPreviewUrl);
    }
    setSelectedVideoFile(null);
    setSelectedVideoName("");
    setSelectedVideoPreviewUrl("");
    if (videoInputRef.current) {
      videoInputRef.current.value = "";
    }
  };

  const setSelectedVideoFromFile = (file: File) => {
    const previousUrl = selectedVideoPreviewUrl;
    const nextUrl = URL.createObjectURL(file);
    if (previousUrl && previousUrl.startsWith("blob:")) {
      URL.revokeObjectURL(previousUrl);
    }
    setSelectedVideoFile(file);
    setSelectedVideoName(file.name);
    setSelectedVideoPreviewUrl(nextUrl);
  };

  const setSelectedAudioFromFile = (file: File) => {
    const previousUrl = selectedAudioPreviewUrl;
    const nextUrl = URL.createObjectURL(file);
    if (previousUrl && previousUrl.startsWith("blob:")) {
      URL.revokeObjectURL(previousUrl);
    }
    setSelectedAudioFile(file);
    setSelectedAudioName(file.name);
    setSelectedAudioPreviewUrl(nextUrl);
  };

  const handleSelectVideoFile = (file: File | null) => {
    if (!file) {
      return;
    }

    if (!file.type.startsWith("video/")) {
      alert("请选择视频文件");
      return;
    }
    if (file.size > 256 * 1024 * 1024) {
      alert("视频大小不能超过 256MB");
      return;
    }

    setSelectedVideoFromFile(file);
    if (videoInputRef.current) {
      videoInputRef.current.value = "";
    }
  };

  const resolveRecordingExtension = (mimeType: string) => {
    const normalized = mimeType.toLowerCase();
    if (normalized.includes("ogg")) return "ogg";
    if (normalized.includes("mp4")) return "m4a";
    if (normalized.includes("mpeg") || normalized.includes("mp3")) return "mp3";
    if (normalized.includes("wav")) return "wav";
    return "webm";
  };

  const startAudioRecording = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("当前浏览器不支持录音");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const preferredMimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
      ];
      const selectedMimeType = preferredMimeTypes.find((item) => MediaRecorder.isTypeSupported(item)) || "";
      const recorder = selectedMimeType
        ? new MediaRecorder(stream, { mimeType: selectedMimeType })
        : new MediaRecorder(stream);

      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        clearRecordingTimer();
        setIsRecordingAudio(false);
        const chunkList = [...audioChunksRef.current];
        audioChunksRef.current = [];
        stopMediaStreamTracks();
        if (!chunkList.length) {
          return;
        }
        const finalMimeType = recorder.mimeType || "audio/webm";
        const audioBlob = new Blob(chunkList, { type: finalMimeType });
        const extension = resolveRecordingExtension(finalMimeType);
        const audioFile = new File([audioBlob], `voice-${Date.now()}.${extension}`, {
          type: finalMimeType,
        });
        setSelectedAudioFromFile(audioFile);
        setShouldAutoSubmitRecordedAudio(true);
      };

      mediaRecorderRef.current = recorder;
      clearRecordingTimer();
      setRecordingElapsedSeconds(0);
      recordingTimerRef.current = window.setInterval(() => {
        setRecordingElapsedSeconds((value) => value + 1);
      }, 1000);
      recorder.start(250);
      setIsRecordingAudio(true);
    } catch (error) {
      stopMediaStreamTracks();
      clearRecordingTimer();
      setIsRecordingAudio(false);
      console.error("录音启动失败:", error);
      alert("无法启动录音，请检查麦克风权限");
    }
  };

  const stopAudioRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) {
      setIsRecordingAudio(false);
      stopMediaStreamTracks();
      return;
    }
    if (recorder.state !== "inactive") {
      recorder.stop();
    } else {
      clearRecordingTimer();
      setIsRecordingAudio(false);
      stopMediaStreamTracks();
    }
  };

  const toggleAudioRecording = async () => {
    if (isRecordingAudio) {
      stopAudioRecording();
      return;
    }
    await startAudioRecording();
  };

  const handleSelectAudioFile = (file: File | null) => {
    if (!file) {
      return;
    }

    if (!file.type.startsWith("audio/")) {
      alert("请选择音频文件");
      return;
    }
    if (file.size > 32 * 1024 * 1024) {
      alert("音频大小不能超过 32MB");
      return;
    }

    setShouldAutoSubmitRecordedAudio(false);
    setSelectedAudioFromFile(file);
    if (audioInputRef.current) {
      audioInputRef.current.value = "";
    }
  };

  useEffect(() => {
    if (!shouldAutoSubmitRecordedAudio) {
      return;
    }
    if (!selectedAudioFile || isLoading || !isBackendAvailable) {
      return;
    }
    setShouldAutoSubmitRecordedAudio(false);
    window.setTimeout(() => {
      formRef.current?.requestSubmit();
    }, 0);
  }, [shouldAutoSubmitRecordedAudio, selectedAudioFile, isLoading, isBackendAvailable]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setShouldAutoSubmitRecordedAudio(false);
    if ((!input.trim() && selectedImages.length === 0 && !selectedFileData && !selectedAudioFile && !selectedVideoFile) || isLoading) return;
    if (selectedAudioFile && modeConfig?.supports_audio === false) {
      setModeWarnings((prev) => {
        const next = [...prev, `当前档位 ${modeConfig.deploy_profile} 不支持音频输入`];
        return Array.from(new Set(next));
      });
      return;
    }
    if (selectedVideoFile && modeConfig?.supports_video === false) {
      setModeWarnings((prev) => {
        const next = [...prev, `当前档位 ${modeConfig.deploy_profile} 不支持视频输入`];
        return Array.from(new Set(next));
      });
      return;
    }

    if (!isBackendAvailable) {
      setIsLoading(true);
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "⚠️ 后端服务器未连接，请先启动后端服务。",
            timestamp: new Date(),
          },
        ]);
        setIsLoading(false);
      }, 500);
      setInput("");
      setSelectedImages([]);
      setSelectedFileData("");
      setSelectedFileName("");
      setSelectedFileFormat("");
      resetSelectedAudio();
      resetSelectedVideo();
      clearRecordingTimer();
      setRecordingElapsedSeconds(0);
      return;
    }

    const userMessage: ChatMessage = {
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
      has_image: selectedImages.length > 0,
      image_url: selectedImages[0]?.previewDataUrl || undefined,
      image_urls: selectedImages.map((item) => item.previewDataUrl),
      image_format: selectedImages[0]?.format || undefined,
      has_file: !!selectedFileData,
      file_name: selectedFileName || undefined,
      file_format: selectedFileFormat || undefined,
      has_audio: !!selectedAudioFile,
      audio_url: undefined,
      has_video: !!selectedVideoFile,
      video_url: undefined,
    };
    const messageToSend = input.trim();
    const imagePayloadsToSend = selectedImages;
    const fileDataToSend = selectedFileData;
    const fileNameToSend = selectedFileName;
    const fileFormatToSend = selectedFileFormat;
    const audioFileToSend = selectedAudioFile;
    const videoFileToSend = selectedVideoFile;

    setInput("");
    setSelectedImages([]);
    setSelectedFileData("");
    setSelectedFileName("");
    setSelectedFileFormat("");
    resetSelectedAudio();
    resetSelectedVideo();
    clearRecordingTimer();
    setRecordingElapsedSeconds(0);
    setIsLoading(true);

    const assistantMessage: ChatMessage = {
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    const assistantIndex = messagesRef.current.length + 1;
    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setStreamingAssistantIndex(assistantIndex);
    setStreamingAssistantContent("");
    setStreamingThinkingPanelLocked(Boolean(modeConfig?.supports_thinking ? enableThinkingMode : false));
    streamBufferRef.current = "";
    lastStreamFlushAtRef.current = 0;

    try {
      let fullResponse = "";
      const streamResult: { done: StreamDonePayload | null } = { done: null };
      let uploadedImageIds: string[] = [];
      let uploadedImageFormat = imagePayloadsToSend[0]?.format || "jpeg";
      let uploadedAudioUrl: string | undefined;
      let uploadedVideoUrl: string | undefined;
      setModeWarnings([]);

      if (imagePayloadsToSend.length > 0) {
        const uploadResults = await Promise.all(
          imagePayloadsToSend.map((item) => uploadChatImage(item.file))
        );
        uploadedImageIds = uploadResults.map((item) => item.image_id).filter(Boolean);
        uploadedImageFormat = uploadResults[0]?.image_format || uploadedImageFormat;
      }
      if (audioFileToSend) {
        const audioUploadResult = await uploadChatAudio(audioFileToSend);
        const uploadedAudioLocalUrl = `/api/chat/audios/${audioUploadResult.audio_id}`;
        uploadedAudioUrl = uploadedAudioLocalUrl;
        setMessages((prev) => {
          const next = [...prev];
          const userIndex = assistantIndex - 1;
          if (userIndex >= 0 && userIndex < next.length && next[userIndex]?.role === "user") {
            next[userIndex] = {
              ...next[userIndex],
              audio_url: uploadedAudioLocalUrl,
              audio_urls: [uploadedAudioLocalUrl],
            };
          }
          return next;
        });
      }
      if (videoFileToSend) {
        const videoUploadResult = await uploadChatVideo(videoFileToSend);
        const uploadedVideoLocalUrl = `/api/chat/videos/${videoUploadResult.video_id}`;
        uploadedVideoUrl = uploadedVideoLocalUrl;
        setMessages((prev) => {
          const next = [...prev];
          const userIndex = assistantIndex - 1;
          if (userIndex >= 0 && userIndex < next.length && next[userIndex]?.role === "user") {
            next[userIndex] = {
              ...next[userIndex],
              video_url: uploadedVideoLocalUrl,
              video_urls: [uploadedVideoLocalUrl],
            };
          }
          return next;
        });
      }

      for await (const token of streamMessage(
        messageToSend,
        sessionId,
        uploadedImageIds.length === 1 ? uploadedImageIds[0] : undefined,
        uploadedImageFormat,
        fileDataToSend,
        fileNameToSend,
        fileFormatToSend,
        modeConfig?.supports_thinking ? enableThinkingMode : false,
        modeConfig?.supports_tool_calling ? enableToolCallingMode : false,
        (metadata) => {
          const newSessionId = metadata.session_id;
          if (onSessionChange && newSessionId && newSessionId !== sessionId) {
            onSessionChange(newSessionId);
          }
          if (Array.isArray(metadata.mode_warnings) && metadata.mode_warnings.length) {
            setModeWarnings(metadata.mode_warnings.map((item) => String(item)));
          }
          if (typeof metadata.enable_thinking === "boolean") {
            setStreamingThinkingPanelLocked(metadata.enable_thinking);
          }
          const multimodalMode = String(metadata.multimodal_mode || "");
          const usesGemma4NativeImagePath = (
            multimodalMode === "gemma4_native"
            || multimodalMode === "gemma4_native_image"
            || multimodalMode === "gemma4_native_image_audio"
            || multimodalMode === "gemma4_native_image_video"
            || multimodalMode === "gemma4_native_image_video_audio"
          );
          if (uploadedImageIds.length > 0 && multimodalMode && !usesGemma4NativeImagePath) {
            setModeWarnings((prev) => {
              const next = [...prev, `图片请求未走 Gemma4 原生多模态链路（当前: ${multimodalMode}）`];
              return Array.from(new Set(next));
            });
          }
          if (uploadedAudioUrl && multimodalMode && !multimodalMode.includes("audio")) {
            setModeWarnings((prev) => {
              const next = [...prev, `音频请求未走 Gemma4 原生音频链路（当前: ${multimodalMode}）`];
              return Array.from(new Set(next));
            });
          }
          if (uploadedVideoUrl && multimodalMode && !multimodalMode.includes("video")) {
            setModeWarnings((prev) => {
              const next = [...prev, `视频请求未走 Gemma4 原生视频链路（当前: ${multimodalMode}）`];
              return Array.from(new Set(next));
            });
          }
        },
        (done) => {
          streamResult.done = done;
        },
        uploadedImageIds.length > 1 ? uploadedImageIds : undefined,
        uploadedAudioUrl,
        undefined,
        uploadedVideoUrl,
      )) {
        fullResponse += token;
        streamBufferRef.current = fullResponse;
        const now = Date.now();
        if (now - lastStreamFlushAtRef.current >= STREAM_FLUSH_INTERVAL_MS) {
          lastStreamFlushAtRef.current = now;
          setStreamingAssistantContent(streamBufferRef.current);
        }
      }

      const rawFullContent = (streamResult.done?.full_content || fullResponse || "").trim();
      const doneDisplayContent = (streamResult.done?.display_content || "").trim();
      const doneReasoningContent = (streamResult.done?.reasoning_content || "").trim();
      const doneFinalContent = (streamResult.done?.final_content || "").trim();

      let reasoningContent = doneReasoningContent || undefined;
      let finalContent = doneFinalContent || doneDisplayContent || rawFullContent;
      let displayContent = doneDisplayContent || doneFinalContent || rawFullContent;

      if (!reasoningContent && /^thought\s*/i.test(rawFullContent)) {
        const parsed = parseThinkingContent(rawFullContent);
        const parsedReasoning = parsed?.reasoning?.trim() || "";
        const parsedAnswer = parsed?.answer?.trim() || "";
        if (parsedReasoning) {
          reasoningContent = parsedReasoning;
          if (!doneFinalContent && parsedAnswer) {
            finalContent = parsedAnswer;
          }
          if (!doneDisplayContent && parsedAnswer) {
            displayContent = parsedAnswer;
          }
        }
      }

      if (!finalContent) {
        finalContent = displayContent || rawFullContent;
      }
      if (!displayContent) {
        displayContent = finalContent || rawFullContent;
      }
      setStreamingAssistantContent(fullResponse);
      setMessages((prev) => {
        const newMessages = [...prev];
        const fallbackIndex = newMessages
          .map((msg, index) => ({ msg, index }))
          .reverse()
          .find((item) => item.msg.role === "assistant")?.index;
        const targetIndex = assistantIndex >= 0 && assistantIndex < newMessages.length
          ? assistantIndex
          : fallbackIndex;
        if (typeof targetIndex === "number") {
          newMessages[targetIndex] = {
            ...newMessages[targetIndex],
            content: displayContent,
            reasoning_content: reasoningContent,
            final_content: finalContent,
          };
        }
        return newMessages;
      });
      setIsBackendAvailable(true);

      if (onRefreshSessions) {
        onRefreshSessions();
      }
    } catch (error) {
      if (isNetworkError(error)) {
        setIsBackendAvailable(false);
      }
      setMessages((prev) => {
        const newMessages = [...prev];
        const fallbackIndex = newMessages
          .map((msg, index) => ({ msg, index }))
          .reverse()
          .find((item) => item.msg.role === "assistant")?.index;
        const targetIndex = assistantIndex >= 0 && assistantIndex < newMessages.length
          ? assistantIndex
          : fallbackIndex;
        if (typeof targetIndex === "number") {
          newMessages[targetIndex] = {
            ...newMessages[targetIndex],
            content: isNetworkError(error)
              ? "⚠️ 后端服务器未连接，请先启动后端服务。"
              : `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
          };
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
      setStreamingAssistantIndex(null);
      setStreamingAssistantContent("");
      setStreamingThinkingPanelLocked(false);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSelectFile = async (file: File | null) => {
    if (!file) {
      return;
    }

    const allowed = new Set(["txt", "md", "markdown", "pdf", "csv", "json", "log"]);
    const ext = file.name.includes(".") ? file.name.split(".").pop()?.toLowerCase() || "" : "";
    if (!allowed.has(ext)) {
      alert("暂仅支持 txt/md/pdf/csv/json/log 文件");
      return;
    }

    if (file.size > 64 * 1024 * 1024) {
      alert("文件大小不能超过 64MB");
      return;
    }

    try {
      const base64Data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = reader.result;
          if (typeof result !== "string" || !result.includes(",")) {
            reject(new Error("文件读取失败"));
            return;
          }
          resolve(result.split(",", 2)[1]);
        };
        reader.onerror = () => reject(new Error("文件读取失败"));
        reader.readAsDataURL(file);
      });

      setSelectedFileData(base64Data);
      setSelectedFileName(file.name);
      setSelectedFileFormat(ext);
    } catch (error) {
      console.error("文件处理失败:", error);
      alert("文件处理失败，请重试");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const clearSelectedFile = () => {
    setSelectedFileData("");
    setSelectedFileName("");
    setSelectedFileFormat("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const resolveMessageAudioSources = (msg: ChatMessage): string[] => {
    const sources: string[] = [];
    if (Array.isArray(msg.audio_urls) && msg.audio_urls.length > 0) {
      sources.push(...msg.audio_urls);
    }
    if (msg.audio_url) {
      sources.push(msg.audio_url);
    }
    return Array.from(
      new Set(
        sources
          .map((item) => resolveApiUrl(item) || item)
          .filter((item) => Boolean(item) && !String(item).startsWith("blob:"))
      )
    );
  };

  const resolveMessageVideoSources = (msg: ChatMessage): string[] => {
    const sources: string[] = [];
    if (Array.isArray(msg.video_urls) && msg.video_urls.length > 0) {
      sources.push(...msg.video_urls);
    }
    if (msg.video_url) {
      sources.push(msg.video_url);
    }
    return Array.from(
      new Set(
        sources
          .map((item) => resolveApiUrl(item) || item)
          .filter((item) => Boolean(item) && !String(item).startsWith("blob:"))
      )
    );
  };

  const currentProfileGuide =
    modeConfig?.deploy_profile && modeConfig.deploy_profile in PROFILE_GUIDE
      ? PROFILE_GUIDE[modeConfig.deploy_profile as DeployProfileKey]
      : null;

  const imageUploadDisabledReason = !isBackendAvailable
    ? "后端服务未连接"
    : isLoading
      ? "正在生成回复，请稍候"
      : modeConfig?.supports_image === false
        ? `当前服务端档位 ${modeConfig.deploy_profile} 不支持图片，请修改 VLLM_DEPLOY_PROFILE 后重启服务`
        : undefined;
  const audioUploadDisabledReason = !isBackendAvailable
    ? "后端服务未连接"
    : isLoading
      ? "正在生成回复，请稍候"
      : modeConfig?.supports_audio === false
        ? `当前服务端档位 ${modeConfig.deploy_profile} 不支持音频，请修改 VLLM_DEPLOY_PROFILE 后重启服务`
        : undefined;
  const videoUploadDisabledReason = !isBackendAvailable
    ? "后端服务未连接"
    : isLoading
      ? "正在生成回复，请稍候"
      : modeConfig?.supports_video === false
        ? `当前服务端档位 ${modeConfig.deploy_profile} 不支持视频，请修改 VLLM_DEPLOY_PROFILE 后重启服务`
        : undefined;

  const capabilityBadgeClass = (enabled: boolean) =>
    cn(
      "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] border",
      enabled
        ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/30"
        : "bg-muted text-muted-foreground border-border"
    );

  return (
    <div className="flex flex-col h-full bg-background relative">
      {/* Messages Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-smooth">
        <div className="max-w-3xl mx-auto px-4 py-8 space-y-8">
          {/* Connection Warning */}
          {!isBackendAvailable && (
            <div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-3 animate-fade-in">
              <AlertCircle className="w-5 h-5 text-destructive" />
              <p className="text-sm text-destructive-foreground font-medium">
                后端服务器未连接，请先启动后端服务
              </p>
            </div>
          )}

          {/* Loading State */}
          {isLoadingHistory ? (
            <div className="space-y-6 py-4 animate-fade-in">
              {[1, 2, 3].map((i) => (
                <div key={i} className={cn("flex gap-4", i % 2 === 0 ? "justify-end" : "justify-start")}>
                   {i % 2 !== 0 && (
                     <Skeleton className="w-8 h-8 rounded-lg flex-shrink-0" />
                   )}
                   <div className={cn("space-y-2", i % 2 === 0 ? "items-end" : "items-start")}>
                     <Skeleton className={cn("h-10 w-[250px] sm:w-[350px]", i % 2 === 0 ? "rounded-tr-sm" : "rounded-tl-sm")} />
                     <Skeleton className="h-4 w-[150px] opacity-60" />
                   </div>
                   {i % 2 === 0 && (
                     <Skeleton className="w-8 h-8 rounded-lg flex-shrink-0" />
                   )}
                </div>
              ))}
            </div>
          ) : messages.length === 0 ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center py-20 text-center animate-slide-up">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 shadow-sm p-3">
                <Logo size="lg" />
              </div>
              <h2 className="text-2xl font-semibold text-foreground mb-3">
                {sessionId ? "开始新对话..." : "你好！我是 AssistantBot"}
              </h2>
              <p className="text-muted-foreground max-w-md mx-auto leading-relaxed">
                {isBackendAvailable
                  ? "我可以帮你搜索知识库、回答问题，或者只是聊聊天。试着问我点什么吧！"
                  : "请先启动后端服务以开始对话"}
              </p>
            </div>
          ) : (
            /* Messages */
            <div className="space-y-6">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "flex gap-4 animate-slide-up",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1 overflow-hidden">
                      <Logo size="sm" />
                    </div>
                  )}
                  <div
                    className={cn(
                      "max-w-[85%] px-5 py-3.5 shadow-sm",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
                        : "bg-card border border-border text-card-foreground rounded-2xl rounded-tl-sm"
                    )}
                  >
                    {/* Display image if present */}
                    {msg.has_image && (() => {
                      const imageSources: string[] = [];
                      if (Array.isArray(msg.image_urls) && msg.image_urls.length > 0) {
                        imageSources.push(...msg.image_urls);
                      }
                      if (msg.image_url) {
                        imageSources.push(msg.image_url);
                      }
                      if (msg.image_data) {
                        imageSources.push(
                          msg.image_data.startsWith("data:image/")
                            ? msg.image_data
                            : `data:image/${msg.image_format || "png"};base64,${msg.image_data}`
                        );
                      }
                      if (Array.isArray(msg.image_ids) && msg.image_ids.length > 0) {
                        imageSources.push(...msg.image_ids.map((id) => API.chatImage(id)));
                      } else if (msg.image_id) {
                        imageSources.push(API.chatImage(msg.image_id));
                      }
                      const uniqueSources = Array.from(new Set(imageSources.filter(Boolean)));
                      if (!uniqueSources.length) {
                        return null;
                      }
                      return (
                        <div className="mb-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {uniqueSources.map((src, imageIndex) => (
                            <div key={`${src}-${imageIndex}`} className="rounded-lg overflow-hidden">
                              <img
                                src={src}
                                alt={`Uploaded image ${imageIndex + 1}`}
                                className="max-w-full h-auto rounded-lg"
                              />
                            </div>
                          ))}
                        </div>
                      );
                    })()}
                    {msg.has_audio && (() => {
                      const audioSources = resolveMessageAudioSources(msg);
                      if (!audioSources.length) {
                        return (
                          <div className="mb-3 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs border border-border">
                            <Mic className="w-3 h-3" />
                            <span>语音输入</span>
                          </div>
                        );
                      }
                      return (
                        <div className="mb-3 space-y-2">
                          {audioSources.map((src, audioIndex) => (
                            <audio
                              key={`${src}-${audioIndex}`}
                              controls
                              preload="metadata"
                              className="w-full min-w-[220px] max-w-[420px]"
                              src={src}
                            />
                          ))}
                        </div>
                      );
                    })()}
                    {msg.has_video && (() => {
                      const videoSources = resolveMessageVideoSources(msg);
                      if (!videoSources.length) {
                        return (
                          <div className="mb-3 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs border border-border">
                            <Video className="w-3 h-3" />
                            <span>视频输入</span>
                          </div>
                        );
                      }
                      return (
                        <div className="mb-3 space-y-2">
                          {videoSources.map((src, videoIndex) => (
                            <video
                              key={`${src}-${videoIndex}`}
                              controls
                              preload="metadata"
                              className="w-full min-w-[220px] max-w-[420px] rounded-lg"
                              src={src}
                            />
                          ))}
                        </div>
                      );
                    })()}
                    {msg.role === "assistant" ? (
                      <div className="text-sm leading-relaxed">
                        {(() => {
                          const isStreamingMessage = isLoading && streamingAssistantIndex === idx;
                          const contentToRender = isStreamingMessage ? streamingAssistantContent : msg.content;
                          return (
                            <AssistantContent
                              content={contentToRender || ""}
                              isStreaming={isStreamingMessage}
                              reasoningContent={msg.reasoning_content}
                              finalContent={msg.final_content}
                              preferThinkingPanel={isStreamingMessage && streamingThinkingPanelLocked}
                            />
                          );
                        })()}
                      </div>
                    ) : (
                      <div>
                        {msg.has_file && msg.file_name && (
                          <div className="mb-2 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-primary-foreground/20 text-xs">
                            <Paperclip className="w-3 h-3" />
                            <span className="truncate max-w-[220px]" title={msg.file_name}>
                              {msg.file_name}
                            </span>
                          </div>
                        )}
                        {msg.content && (
                          <p className="text-sm whitespace-pre-wrap leading-relaxed">
                            {msg.content}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0 mt-1">
                      <User className="w-5 h-5 text-secondary-foreground" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Input Area */}
      <div className="flex-shrink-0 p-4 bg-background/80 backdrop-blur-sm border-t border-border z-10">
        <form
          ref={formRef}
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto relative group"
        >
          <div className="mb-2 flex items-center gap-2">
            <Button
              type="button"
              variant={enableThinkingMode ? "default" : "outline"}
              size="sm"
              className="h-8 gap-1.5"
              onClick={() => setEnableThinkingMode((value) => !value)}
              disabled={isLoading || !isBackendAvailable || modeConfig?.supports_thinking === false}
              title={
                modeConfig?.supports_thinking === false
                  ? `当前档位 ${modeConfig.deploy_profile} 不支持 Thinking`
                  : "切换 Thinking 模式"
              }
            >
              <Brain className="w-3.5 h-3.5" />
              Thinking
            </Button>
            <Button
              type="button"
              variant={enableToolCallingMode ? "default" : "outline"}
              size="sm"
              className="h-8 gap-1.5"
              onClick={() => setEnableToolCallingMode((value) => !value)}
              disabled={isLoading || !isBackendAvailable || modeConfig?.supports_tool_calling === false}
              title={
                modeConfig?.supports_tool_calling === false
                  ? `当前档位 ${modeConfig.deploy_profile} 不支持 Tool Calling`
                  : "切换 Tool Calling 模式"
              }
            >
              <Wrench className="w-3.5 h-3.5" />
              Tool Calling
            </Button>
            {modeConfig && (
              <Dialog>
                <DialogTrigger className="inline-flex">
                  <button
                    type="button"
                    className="text-xs text-muted-foreground px-2 py-1 rounded-md border border-border inline-flex items-center gap-1.5 hover:border-primary/40 hover:text-foreground transition-colors"
                    title="查看档位说明"
                  >
                    <Info className="w-3.5 h-3.5" />
                    Profile: {modeConfig.deploy_profile}
                  </button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle>Deploy Profile 说明</DialogTitle>
                    <DialogDescription>
                      当前后端档位：<span className="font-medium text-foreground">{modeConfig.deploy_profile}</span>
                      。该档位由 vLLM 启动参数决定，运行中不可切换。
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-2.5">
                    {currentProfileGuide && (
                      <div className="rounded-lg border p-3 border-primary/50 bg-primary/5">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <div className="text-sm font-medium text-foreground">
                            {modeConfig.deploy_profile}
                            <span className="ml-2 text-[11px] text-primary">当前</span>
                          </div>
                          <div className="text-[11px] text-muted-foreground">{currentProfileGuide.title}</div>
                        </div>
                        <p className="text-xs text-muted-foreground mb-2">{currentProfileGuide.description}</p>
                        <div className="flex flex-wrap gap-1.5">
                          <span className={capabilityBadgeClass(currentProfileGuide.supportsImage)}>Image</span>
                          <span className={capabilityBadgeClass(currentProfileGuide.supportsAudio)}>Audio</span>
                          <span className={capabilityBadgeClass(currentProfileGuide.supportsVideo)}>Video</span>
                          <span className={capabilityBadgeClass(currentProfileGuide.supportsThinking)}>Thinking</span>
                          <span className={capabilityBadgeClass(currentProfileGuide.supportsToolCalling)}>Tool Calling</span>
                        </div>
                      </div>
                    )}
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    若需变更能力，请修改服务器启动环境中的 `VLLM_DEPLOY_PROFILE` 并重启 vLLM。
                  </p>
                </DialogContent>
              </Dialog>
            )}
          </div>
          {modeWarnings.length > 0 && (
            <div className="mb-2 text-xs text-amber-600">
              {modeWarnings.join("；")}
            </div>
          )}
          {modeConfig?.supports_image === false && (
            <div className="mb-2 text-xs text-amber-600">
              当前 Profile `{modeConfig.deploy_profile}` 已关闭图片输入。请调整服务器 `VLLM_DEPLOY_PROFILE` 并重启后再使用图片。
            </div>
          )}
          {modeConfig?.supports_audio === false && (
            <div className="mb-2 text-xs text-amber-600">
              当前 Profile `{modeConfig.deploy_profile}` 已关闭音频输入。请调整服务器 `VLLM_DEPLOY_PROFILE` 并重启后再使用语音。
            </div>
          )}
          {modeConfig?.supports_video === false && (
            <div className="mb-2 text-xs text-amber-600">
              当前 Profile `{modeConfig.deploy_profile}` 已关闭视频输入。请调整服务器 `VLLM_DEPLOY_PROFILE` 并重启后再使用视频理解。
            </div>
          )}
          {isRecordingAudio && (
            <div className="mb-2 text-xs text-rose-600">
              录音中 {formatRecordingDuration(recordingElapsedSeconds)}，点击方块停止后将自动发送给 Gemma4
            </div>
          )}
          {currentProfileGuide && (
            <div className="mb-2 text-[11px] text-muted-foreground">
              当前档位能力：Image {currentProfileGuide.supportsImage ? "ON" : "OFF"} / Audio {currentProfileGuide.supportsAudio ? "ON" : "OFF"} / Video {currentProfileGuide.supportsVideo ? "ON" : "OFF"} / Thinking {currentProfileGuide.supportsThinking ? "ON" : "OFF"} / Tool Calling {currentProfileGuide.supportsToolCalling ? "ON" : "OFF"}
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf,.csv,.json,.log"
            className="hidden"
            disabled={isLoading || !isBackendAvailable}
            onChange={(e) => handleSelectFile(e.target.files?.[0] || null)}
          />
          <input
            ref={videoInputRef}
            type="file"
            accept="video/*"
            className="hidden"
            disabled={isLoading || !isBackendAvailable || modeConfig?.supports_video === false}
            onChange={(e) => handleSelectVideoFile(e.target.files?.[0] || null)}
          />
          <input
            ref={audioInputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            disabled={isLoading || !isBackendAvailable || modeConfig?.supports_audio === false}
            onChange={(e) => handleSelectAudioFile(e.target.files?.[0] || null)}
          />
          <div className="flex items-end gap-4">
            {/* Image uploader - 独立在输入框左侧 */}
            <div className="flex-shrink-0">
              <ImageUploader
                value={selectedImages}
                onImagesChange={(payloads: SelectedImagePayload[]) => {
                  setSelectedImages(payloads);
                }}
                disabled={
                  isLoading ||
                  !isBackendAvailable ||
                  modeConfig?.supports_image === false
                }
                disabledReason={imageUploadDisabledReason}
                maxImages={4}
              />
            </div>

            <div className="flex-shrink-0">
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading || !isBackendAvailable}
                className={cn(
                  "h-12 w-12 rounded-2xl shadow-sm",
                  selectedFileData && "border-primary text-primary"
                )}
                title="上传文件附件"
              >
                <Paperclip className="w-5 h-5" />
              </Button>
            </div>
            <div className="flex-shrink-0">
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={() => videoInputRef.current?.click()}
                disabled={Boolean(videoUploadDisabledReason)}
                className={cn(
                  "h-12 w-12 rounded-2xl shadow-sm",
                  selectedVideoFile && "border-primary text-primary"
                )}
                title={videoUploadDisabledReason || "上传视频文件"}
              >
                <Video className="w-5 h-5" />
              </Button>
            </div>
            <div className="flex-shrink-0">
              <Button
                type="button"
                size="icon"
                variant={isRecordingAudio ? "default" : "outline"}
                onClick={toggleAudioRecording}
                disabled={Boolean(audioUploadDisabledReason)}
                className="h-12 w-12 rounded-2xl shadow-sm"
                title={audioUploadDisabledReason || (isRecordingAudio ? "停止录音并自动发送" : "开始录音")}
              >
                {isRecordingAudio ? <Square className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
              </Button>
            </div>

            {/* Input wrapper */}
            <div className={cn(
              "relative flex-1 flex flex-col bg-card border border-input rounded-2xl shadow-lg transition-all duration-300",
              "focus-within:ring-2 focus-within:ring-ring focus-within:border-primary/50 focus-within:shadow-xl",
              "hover:border-primary/30 hover:shadow-md"
            )}>
              {/* 背景装饰 - 光泽效果 */}
              <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />

              {selectedFileData && selectedFileName && (
                <div className="px-3 pt-3 pb-1">
                  <div className="inline-flex max-w-full items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs border border-border">
                    <Paperclip className="w-3 h-3 flex-shrink-0" />
                    <span className="max-w-[220px] sm:max-w-[320px] truncate" title={selectedFileName}>
                      {selectedFileName}
                    </span>
                    <button
                      type="button"
                      onClick={clearSelectedFile}
                      className="text-muted-foreground hover:text-foreground flex-shrink-0"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}
              {selectedAudioFile && (
                <div className="px-3 pt-3 pb-1">
                  <div className="inline-flex max-w-full items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs border border-border">
                    <Mic className="w-3 h-3 flex-shrink-0" />
                    <span className="max-w-[220px] sm:max-w-[320px] truncate" title={selectedAudioName || selectedAudioFile.name}>
                      {selectedAudioName || selectedAudioFile.name}
                    </span>
                    <button
                      type="button"
                      onClick={resetSelectedAudio}
                      className="text-muted-foreground hover:text-foreground flex-shrink-0"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                  {selectedAudioPreviewUrl && (
                    <audio
                      className="mt-2 w-full max-w-[360px]"
                      controls
                      preload="metadata"
                      src={selectedAudioPreviewUrl}
                    />
                  )}
                </div>
              )}
              {selectedVideoFile && (
                <div className="px-3 pt-3 pb-1">
                  <div className="inline-flex max-w-full items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs border border-border">
                    <Video className="w-3 h-3 flex-shrink-0" />
                    <span className="max-w-[220px] sm:max-w-[320px] truncate" title={selectedVideoName || selectedVideoFile.name}>
                      {selectedVideoName || selectedVideoFile.name}
                    </span>
                    <button
                      type="button"
                      onClick={resetSelectedVideo}
                      className="text-muted-foreground hover:text-foreground flex-shrink-0"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                  {selectedVideoPreviewUrl && (
                    <video
                      className="mt-2 w-full max-w-[420px] rounded-lg"
                      controls
                      preload="metadata"
                      src={selectedVideoPreviewUrl}
                    />
                  )}
                </div>
              )}

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isBackendAvailable
                    ? "发送消息... (Enter 发送, Shift+Enter 换行)"
                    : "后端服务未启动..."
                }
                className={cn(
                  "flex-1 min-h-[52px] max-h-[200px] px-4 py-3.5 bg-transparent text-foreground placeholder:text-muted-foreground resize-none focus:outline-none text-sm leading-relaxed pr-14 rounded-2xl"
                )}
                disabled={isLoading || !isBackendAvailable}
                rows={1}
                style={{
                  height: "auto",
                }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = "auto";
                  target.style.height = Math.min(target.scrollHeight, 200) + "px";
                }}
              />
              <Button
                type="submit"
                size="icon"
                disabled={(!input.trim() && selectedImages.length === 0 && !selectedFileData && !selectedAudioFile && !selectedVideoFile) || isLoading || !isBackendAvailable}
                className={cn(
                  "absolute right-2 bottom-2 transition-all duration-300 h-10 w-10 rounded-xl",
                  (input.trim() || selectedImages.length > 0 || selectedFileData || selectedAudioFile || selectedVideoFile) && !isLoading && isBackendAvailable
                    ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-105 shadow-lg shadow-primary/20"
                    : "bg-muted text-muted-foreground cursor-not-allowed hover:bg-muted"
                )}
              >
                {isLoading ? (
                  <Loader2 className="w-4.5 h-4.5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </Button>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground/80 mt-2.5 text-center flex items-center justify-center gap-1.5">
            <span className="inline-flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-primary/60 animate-pulse" />
              支持文本/RAG/图片/音频/视频/文件，Thinking 与 Tool Calling 由服务端档位控制
            </span>
          </p>
        </form>
      </div>
    </div>
  );
}
